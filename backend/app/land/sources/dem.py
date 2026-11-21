from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject as warp
from scipy.ndimage import distance_transform_edt
from shapely.geometry.base import BaseGeometry

from app.land.cache import DAY, cache
from app.land.geo import PL_CRS, reproject
from app.land.net import client
from app.land.settings import land_settings
from app.land.sources.cog import GDAL_ENV, semaphore

NMT_POINTS_URL = "https://services.gugik.gov.pl/nmt/"
NMT_BATCH = 1000
NMT_MAX_POINTS = 30_000
NMT_MIN_RES = 2.0
NMT_CONCURRENCY = 16
NMT_TIMEOUT_S = 14.0
COPDEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
MAX_CELLS = 160_000


@dataclass
class Dem:
    data: np.ndarray
    transform: rasterio.Affine
    resolution_m: float
    source: str


def target_grid(
    bounds: tuple[float, float, float, float], min_res: float, max_cells: int = MAX_CELLS
) -> tuple[rasterio.Affine, int, int, float]:
    minx, miny, maxx, maxy = bounds
    area = (maxx - minx) * (maxy - miny)
    res = max(min_res, math.sqrt(area / max_cells))
    res = math.ceil(res * 2) / 2
    width = max(8, math.ceil((maxx - minx) / res))
    height = max(8, math.ceil((maxy - miny) / res))
    transform = rasterio.Affine(res, 0, minx, 0, -res, maxy)
    return transform, width, height, res


def _resample(path: str, transform, width, height) -> np.ndarray:
    out = np.full((height, width), np.nan, dtype=np.float32)
    with rasterio.Env(**GDAL_ENV), rasterio.open(path) as src:
        _warp_into(src, out, transform)
    return out


def _warp_into(src, out: np.ndarray, transform) -> None:
    nodata = src.nodata if src.nodata is not None else -9999.0
    buffer = np.full(out.shape, np.nan, dtype=np.float32)
    warp(
        source=rasterio.band(src, 1),
        destination=buffer,
        src_transform=src.transform,
        src_crs=src.crs,
        src_nodata=nodata,
        dst_transform=transform,
        dst_crs=f"EPSG:{PL_CRS}",
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    take = np.isfinite(buffer) & ~np.isfinite(out) & (buffer > -500)
    out[take] = buffer[take]


def parse_heights(text: str) -> dict[tuple[str, str], float]:
    out = {}
    for item in text.strip().split(","):
        parts = item.split()
        if len(parts) != 3:
            continue
        try:
            value = float(parts[2])
        except ValueError:
            continue
        if value != 0.0:
            out[(parts[0], parts[1])] = value
    return out


async def _height_batch(points: list[tuple[str, str]], limit: asyncio.Semaphore) -> dict[tuple[str, str], float]:
    async with limit:
        response = await client().post(
            NMT_POINTS_URL,
            data={"request": "GetHByPointList", "list": ",".join(f"{n} {e}" for n, e in points)},
            timeout=land_settings().source_timeout_s,
        )
        response.raise_for_status()
        return parse_heights(response.text)


async def _fetch_nmt_points(transform: rasterio.Affine, width: int, height: int) -> np.ndarray:
    res = transform.a
    keys = []
    for row in range(height):
        north = f"{transform.f - (row + 0.5) * res:.1f}"
        for col in range(width):
            keys.append((north, f"{transform.c + (col + 0.5) * res:.1f}"))
    limit = asyncio.Semaphore(NMT_CONCURRENCY)
    batches = [keys[i : i + NMT_BATCH] for i in range(0, len(keys), NMT_BATCH)]
    results = await asyncio.gather(*[_height_batch(b, limit) for b in batches], return_exceptions=True)
    heights: dict[tuple[str, str], float] = {}
    for result in results:
        if isinstance(result, dict):
            heights.update(result)
    values = np.array([heights.get(k, np.nan) for k in keys], dtype=np.float32)
    return values.reshape(height, width)


def _fill_gaps(data: np.ndarray) -> np.ndarray:
    if np.isfinite(data).all():
        return data
    filled = data.copy()
    mask = ~np.isfinite(filled)
    index = distance_transform_edt(mask, return_distances=False, return_indices=True)
    filled[mask] = data[tuple(i[mask] for i in index)]
    return filled


def _copdem_tiles(bounds_wgs84) -> list[str]:
    minx, miny, maxx, maxy = bounds_wgs84
    names = []
    for lat in range(math.floor(miny), math.floor(maxy) + 1):
        for lon in range(math.floor(minx), math.floor(maxx) + 1):
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            names.append(f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM")
    return names


async def load(geom_2180: BaseGeometry, buffer_m: float) -> Dem | None:
    bounds = geom_2180.buffer(buffer_m).bounds
    key = cache.make_key("dem", [round(b, 1) for b in bounds])
    cached = cache.get(key)
    nmt_transform, w1, h1, res1 = target_grid(bounds, NMT_MIN_RES, NMT_MAX_POINTS)
    if cached is not None:
        meta = cache.get(key + ":meta")
        if meta is not None:
            data = np.frombuffer(cached, dtype=np.float32).reshape(meta["h"], meta["w"]).copy()
            return Dem(data, rasterio.Affine(*meta["t"]), meta["res"], meta["source"])
    nmt_task = asyncio.create_task(_fetch_nmt_points(nmt_transform, w1, h1))
    cop_task = asyncio.create_task(_load_copdem(geom_2180, buffer_m, bounds))
    dem: Dem | None = None
    try:
        data = await asyncio.wait_for(nmt_task, NMT_TIMEOUT_S)
    except Exception:
        data = None
    if data is not None and np.isfinite(data).mean() > 0.9:
        dem = Dem(_fill_gaps(data), nmt_transform, res1, "nmt")
        cop_task.cancel()
    if dem is None:
        dem = await cop_task
    if dem is None:
        return None
    cache.set(key, dem.data.astype(np.float32).tobytes(), 30 * DAY)
    cache.set(
        key + ":meta",
        {
            "h": dem.data.shape[0],
            "w": dem.data.shape[1],
            "t": list(dem.transform)[:6],
            "res": dem.resolution_m,
            "source": dem.source,
        },
        30 * DAY,
    )
    return dem


async def _load_copdem(geom_2180: BaseGeometry, buffer_m: float, bounds) -> Dem | None:
    transform, width, height, res = target_grid(bounds, 10.0)
    bounds_wgs84 = reproject(geom_2180.buffer(buffer_m + 100), PL_CRS, 4326).bounds
    data = np.full((height, width), np.nan, dtype=np.float32)
    for name in _copdem_tiles(bounds_wgs84):
        url = COPDEM_URL.format(name=name)
        try:
            head = await client().head(url, timeout=land_settings().source_timeout_s)
        except Exception:
            continue
        if head.status_code != 200:
            continue
        href = "/vsicurl/" + url
        try:
            async with semaphore():
                part = await asyncio.to_thread(_resample, href, transform, width, height)
        except Exception:
            continue
        take = np.isfinite(part) & ~np.isfinite(data)
        data[take] = part[take]
    if np.isfinite(data).mean() < 0.9:
        return None
    return Dem(data, transform, res, "copdem")
