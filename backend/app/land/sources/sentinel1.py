from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timedelta

import numpy as np
from rasterio.windows import Window
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.land.engine.satellite_indices import coverage_weights
from app.land.geo import PL_CRS, reproject
from app.land.models import RadarObservation
from app.land.sources import planetary
from app.land.sources.cog import aligned_window, asset_transform, gather_within, read_window_async, source_transform

COLLECTION = "sentinel-1-rtc"
ASSETS = ("vv", "vh")


async def search(bbox, start: date, end: date, limit: int = 40) -> list[dict]:
    return await planetary.search(COLLECTION, bbox, start, end, ASSETS, limit)


def _covering(items: list[dict], geom_wgs84: BaseGeometry) -> list[dict]:
    return [
        i for i in items if "vv" in i["assets"] and "vh" in i["assets"] and shape(i["geometry"]).contains(geom_wgs84)
    ]


def _db(value: float) -> float:
    return float(10 * np.log10(max(value, 1e-6)))


async def observe(item: dict, geom_2180: BaseGeometry) -> RadarObservation | None:
    token = await planetary.sas_token(COLLECTION)
    geom = reproject(geom_2180, PL_CRS, planetary.epsg(item))
    vv_href = item["assets"]["vv"]["href"] + "?" + token
    vh_href = item["assets"]["vh"]["href"] + "?" + token
    transform = asset_transform(item["assets"]["vv"]) or await asyncio.to_thread(source_transform, vv_href)
    grid = aligned_window(transform, geom.buffer(30).bounds, 1)
    window = Window(grid.col_off, grid.row_off, grid.width, grid.height)
    vv, vh = await asyncio.gather(read_window_async(vv_href, window), read_window_async(vh_href, window))
    weights = coverage_weights(geom, grid.transform, vv.shape)
    valid = (vv > 0) & (vh > 0) & np.isfinite(vv) & np.isfinite(vh)
    w = weights * valid
    if w.sum() < 0.5 or w.sum() < 0.5 * weights.sum():
        return None
    vv_mean = float((vv[valid] * w[valid]).sum() / w[valid].sum())
    vh_mean = float((vh[valid] * w[valid]).sum() / w[valid].sum())
    day = datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00")).date()
    return RadarObservation(
        date=day,
        scene_id=item["id"],
        vv_db=round(_db(vv_mean), 2),
        vh_db=round(_db(vh_mean), 2),
        vh_vv_db=round(_db(vh_mean) - _db(vv_mean), 2),
    )


async def _safe(item, geom_2180):
    try:
        return await observe(item, geom_2180)
    except Exception:
        return None


async def latest_and_history(
    geom_2180: BaseGeometry, geom_wgs84: BaseGeometry, bbox, day: date, years: int, timeout_s: float
):
    started = time.monotonic()
    items = _covering(await search(bbox, day - timedelta(days=12), day), geom_wgs84)
    items.sort(key=lambda i: i["properties"]["datetime"], reverse=True)
    current = None
    orbit = None
    for item in items[:3]:
        remaining = timeout_s - (time.monotonic() - started)
        if remaining <= 1:
            break
        try:
            current = await asyncio.wait_for(_safe(item, geom_2180), remaining)
        except TimeoutError:
            current = None
        if current is not None:
            orbit = item["properties"].get("sat:relative_orbit")
            break
    if current is None:
        return None, []

    async def one_year(offset: int):
        try:
            target = current.date.replace(year=current.date.year - offset)
        except ValueError:
            target = current.date.replace(year=current.date.year - offset, day=28)
        if target < date(2017, 1, 1):
            return None
        candidates = _covering(await search(bbox, target - timedelta(days=10), target + timedelta(days=10)), geom_wgs84)
        candidates.sort(
            key=lambda i: (
                i["properties"].get("sat:relative_orbit") != orbit,
                abs((date.fromisoformat(i["properties"]["datetime"][:10]) - target).days),
            )
        )
        for item in candidates[:2]:
            observation = await _safe(item, geom_2180)
            if observation is not None:
                return observation
        return None

    results = await gather_within([one_year(k) for k in range(1, years + 1)], timeout_s - (time.monotonic() - started))
    return current, [r for r in results if isinstance(r, RadarObservation)]
