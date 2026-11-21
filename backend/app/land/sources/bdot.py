from __future__ import annotations

import asyncio
import io
import math
from dataclasses import dataclass

import matplotlib.image as mpimg
import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt
from shapely.geometry.base import BaseGeometry

from app.land.cache import DAY, cache
from app.land.models import DataStatus, HydroInfo
from app.land.net import client
from app.land.settings import land_settings

WMS_URL = "https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer"
GROUPS = {
    "ditch": "row",
    "watercourse": "rz,rzOk,kan,kanOkr",
    "water": "WPow",
    "wetland": "Mo,Szu",
    "trees": "TLes,RKr",
    "hydrotech": "BHydL,BHydA,Prze",
}
RADIUS_M = 500.0
MAX_PX = 2000


@dataclass
class HydroLayers:
    masks: dict[str, np.ndarray]
    transform: rasterio.Affine
    resolution_m: float


def grid(geom_2180: BaseGeometry, radius_m: float) -> tuple[rasterio.Affine, int, int, float, tuple]:
    minx, miny, maxx, maxy = geom_2180.buffer(radius_m).bounds
    extent = max(maxx - minx, maxy - miny)
    res = max(2.5, math.ceil(extent / MAX_PX * 2) / 2)
    width = math.ceil((maxx - minx) / res)
    height = math.ceil((maxy - miny) / res)
    maxx = minx + width * res
    miny = maxy - height * res
    return rasterio.Affine(res, 0, minx, 0, -res, maxy), width, height, res, (minx, miny, maxx, maxy)


async def _layer(group: str, layers: str, bounds, width: int, height: int) -> np.ndarray:
    key = cache.make_key("bdot", group, [round(b, 1) for b in bounds], width, height)
    cached = cache.get(key)
    if cached is None:
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": layers,
            "STYLES": "",
            "SRS": "EPSG:2180",
            "BBOX": ",".join(f"{b:.2f}" for b in bounds),
            "WIDTH": width,
            "HEIGHT": height,
            "FORMAT": "image/png",
            "TRANSPARENT": "TRUE",
        }
        response = await client().get(WMS_URL, params=params, timeout=land_settings().source_timeout_s)
        response.raise_for_status()
        if not response.headers.get("content-type", "").startswith("image/png"):
            raise ValueError("BDOT10k WMS did not return an image")
        cached = response.content
        cache.set(key, cached, 30 * DAY)
    image = mpimg.imread(io.BytesIO(cached), format="png")
    if image.ndim == 3 and image.shape[-1] == 4:
        return image[..., 3] > 0.1
    return np.zeros((height, width), dtype=bool)


async def load(geom_2180: BaseGeometry, radius_m: float = RADIUS_M) -> HydroLayers:
    transform, width, height, res, bounds = grid(geom_2180, radius_m)
    results = await asyncio.gather(
        *[_layer(group, layers, bounds, width, height) for group, layers in GROUPS.items()], return_exceptions=True
    )
    masks = {}
    for group, result in zip(GROUPS, results, strict=True):
        if isinstance(result, Exception):
            continue
        masks[group] = result
    return HydroLayers(masks, transform, res)


def summarize(layers: HydroLayers, geom_2180: BaseGeometry, radius_m: float = RADIUS_M) -> HydroInfo:
    any_mask = next(iter(layers.masks.values()), None)
    if any_mask is None:
        return HydroInfo(status=DataStatus.missing, search_radius_m=radius_m)
    shape = any_mask.shape
    res = layers.resolution_m
    parcel = rasterize(
        [(geom_2180, 1)], out_shape=shape, transform=layers.transform, fill=0, dtype="uint8", all_touched=True
    ).astype(bool)
    ring = rasterize(
        [(geom_2180.buffer(radius_m), 1)], out_shape=shape, transform=layers.transform, fill=0, dtype="uint8"
    ).astype(bool)
    ring_only = ring & ~parcel
    cell_ha = res * res / 1e4

    def distance(group: str) -> float | None:
        mask = layers.masks.get(group)
        if mask is None or not (mask & ring).any():
            return None
        if (mask & parcel).any():
            return 0.0
        dist = distance_transform_edt(~mask) * res
        return round(float(dist[parcel].min()), 0)

    def area(group: str) -> float:
        mask = layers.masks.get(group)
        return round(float((mask & ring).sum() * cell_ha), 2) if mask is not None else 0.0

    trees = layers.masks.get("trees")
    tree_pct = round(float((trees & ring_only).sum() / max(ring_only.sum(), 1) * 100), 1) if trees is not None else 0.0
    parcel_cells = max(int(parcel.sum()), 1)

    def parcel_share(group: str) -> float:
        mask = layers.masks.get(group)
        return round(float((mask & parcel).sum() / parcel_cells * 100), 1) if mask is not None else 0.0

    missing = [g for g in GROUPS if g not in layers.masks]
    return HydroInfo(
        ditch_distance_m=distance("ditch"),
        watercourse_distance_m=distance("watercourse"),
        water_body_distance_m=distance("water"),
        wetland_distance_m=distance("wetland"),
        ditch_in_parcel=bool(layers.masks.get("ditch") is not None and (layers.masks["ditch"] & parcel).any()),
        watercourse_in_parcel=bool(
            layers.masks.get("watercourse") is not None and (layers.masks["watercourse"] & parcel).any()
        ),
        water_area_ha_500m=area("water"),
        wetland_area_ha_500m=area("wetland"),
        tree_cover_pct_500m=tree_pct,
        tree_cover_pct_parcel=parcel_share("trees"),
        water_pct_parcel=parcel_share("water"),
        hydrotechnical_within_500m=bool(
            layers.masks.get("hydrotech") is not None and (layers.masks["hydrotech"] & ring).any()
        ),
        search_radius_m=radius_m,
        status=DataStatus.partial if missing else DataStatus.ok,
    )
