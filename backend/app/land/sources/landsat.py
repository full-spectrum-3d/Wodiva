from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

import numpy as np
from rasterio.windows import Window
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.land.cache import DAY, cache
from app.land.engine.satellite_indices import coverage_weights, normalized_difference, summarize
from app.land.geo import PL_CRS, reproject
from app.land.models import SatelliteObservation
from app.land.sources import planetary
from app.land.sources.cog import aligned_window, asset_transform, read_window_async, source_transform

COLLECTION = "landsat-c2-l2"
ASSETS = ("red", "nir08", "swir16", "qa_pixel")
PLATFORMS = {"landsat-5": "Landsat 5", "landsat-7": "Landsat 7", "landsat-8": "Landsat 8", "landsat-9": "Landsat 9"}
QA_INVALID_BITS = 0b111111


def valid_from_qa(qa: np.ndarray) -> np.ndarray:
    return (qa > 0) & ((qa.astype(np.uint16) & QA_INVALID_BITS) == 0)


def _scale_offset(asset: dict) -> tuple[float, float]:
    bands = asset.get("raster:bands") or [{}]
    return float(bands[0].get("scale", 2.75e-05)), float(bands[0].get("offset", -0.2))


async def search(bbox, start: date, end: date) -> list[dict]:
    return await planetary.search(COLLECTION, bbox, start, end, ASSETS, 40, {"eo:cloud_cover": {"lt": 50}})


async def observe(item: dict, geom_2180: BaseGeometry) -> SatelliteObservation | None:
    key = cache.make_key("lsobs", item["id"], geom_2180.wkt)
    cached = cache.get(key)
    if cached is not None:
        return SatelliteObservation.model_validate(cached["obs"]) if cached["obs"] else None
    token = await planetary.sas_token(COLLECTION)
    geom = reproject(geom_2180, PL_CRS, planetary.epsg(item))
    hrefs = {k: item["assets"][k]["href"] + "?" + token for k in ASSETS}
    transform = asset_transform(item["assets"]["red"]) or await asyncio.to_thread(source_transform, hrefs["red"])
    grid = aligned_window(transform, geom.buffer(45).bounds, 1)
    window = Window(grid.col_off, grid.row_off, grid.width, grid.height)
    arrays = dict(
        zip(ASSETS, await asyncio.gather(*[read_window_async(hrefs[k], window) for k in ASSETS]), strict=True)
    )
    bands = {}
    for name in ("red", "nir08", "swir16"):
        scale, offset = _scale_offset(item["assets"][name])
        data = arrays[name].astype(np.float32)
        bands[name] = np.where(data > 0, data * scale + offset, np.nan)
    valid = valid_from_qa(arrays["qa_pixel"]) & np.isfinite(bands["red"]) & np.isfinite(bands["nir08"])
    weights = coverage_weights(geom, grid.transform, arrays["red"].shape)
    stats = summarize(
        {
            "ndvi": normalized_difference(bands["nir08"], bands["red"]),
            "ndmi": normalized_difference(bands["nir08"], bands["swir16"]),
        },
        weights,
        valid,
    )
    observation = None
    if stats["effective_pixels"] >= 0.5:
        observation = SatelliteObservation(
            date=datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00")).date(),
            scene_id=item["id"],
            sensor=PLATFORMS.get(item["properties"].get("platform", ""), "Landsat"),
            ndvi=None if stats["ndvi"] is None else round(stats["ndvi"], 3),
            ndmi=None if stats["ndmi"] is None else round(stats["ndmi"], 3),
            clear_fraction=round(stats["clear_fraction"], 2),
            effective_pixels=round(stats["effective_pixels"], 1),
        )
    cache.set(key, {"obs": observation.model_dump(mode="json") if observation else None}, 365 * DAY)
    return observation


async def same_window(
    geom_2180: BaseGeometry, geom_wgs84: BaseGeometry, bbox, target: date
) -> SatelliteObservation | None:
    items = [
        i
        for i in await search(bbox, target - timedelta(days=16), target + timedelta(days=16))
        if shape(i["geometry"]).contains(geom_wgs84) and all(k in i["assets"] for k in ASSETS)
    ]
    items.sort(
        key=lambda i: (
            i["properties"].get("eo:cloud_cover", 100),
            abs((date.fromisoformat(i["properties"]["datetime"][:10]) - target).days),
        )
    )
    for item in items[:3]:
        try:
            observation = await observe(item, geom_2180)
        except Exception:
            continue
        if observation is not None and observation.clear_fraction >= 0.6:
            return observation
    return None
