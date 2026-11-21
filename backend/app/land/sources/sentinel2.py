from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

import numpy as np
from rasterio.windows import Window
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.land.cache import DAY, cache
from app.land.engine.satellite_indices import coverage_weights, normalized_difference, summarize, valid_mask
from app.land.engine.sharpen import sharpen_band
from app.land.geo import PL_CRS, reproject
from app.land.models import SatelliteObservation
from app.land.net import client
from app.land.settings import land_settings
from app.land.sources import landsat
from app.land.sources.cog import aligned_window, asset_transform, gather_within, read_window_async, source_transform

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
BANDS10 = {"B03": "green", "B04": "red", "B08": "nir"}
BANDS20 = {"B05": "rededge1", "B8A": "nir08", "B11": "swir16", "SCL": "scl"}
LIGHT10 = ("B04", "B08")
LIGHT20 = ("B8A", "B11", "SCL")
SENTINEL2_START = date(2015, 7, 1)
HARMONIZED_BASELINE = "04.00"


def _epsg(item: dict) -> int:
    props = item["properties"]
    if "proj:epsg" in props:
        return int(props["proj:epsg"])
    return int(str(props["proj:code"]).split(":")[1])


def scale_offset(item: dict, asset: dict) -> tuple[float, float]:
    bands = asset.get("raster:bands") or [{}]
    scale = float(bands[0].get("scale", 0.0001))
    props = item["properties"]
    if props.get("earthsearch:boa_offset_applied") is True:
        return scale, 0.0
    if "offset" in bands[0]:
        return scale, float(bands[0]["offset"])
    baseline = str(props.get("s2:processing_baseline", "00.00"))
    return scale, -0.1 if baseline >= HARMONIZED_BASELINE else 0.0


async def search(
    bbox: tuple[float, float, float, float], start: date, end: date, max_cloud: float, limit: int = 30
) -> list[dict]:
    key = cache.make_key("s2search", bbox, str(start), str(end), max_cloud, limit)
    cached = cache.get(key)
    if cached is not None:
        return cached
    body = {
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": limit,
    }
    response = await client().post(STAC_URL, json=body, timeout=land_settings().source_timeout_s)
    response.raise_for_status()
    keep = set(BANDS10.values()) | set(BANDS20.values())
    items = [
        {
            "id": f["id"],
            "geometry": f["geometry"],
            "properties": f["properties"],
            "assets": {k: v for k, v in f["assets"].items() if k in keep},
        }
        for f in response.json().get("features", [])
    ]
    ttl = 30 * DAY if end < date.today() - timedelta(days=30) else DAY / 4
    cache.set(key, items, ttl)
    return items


def _covering(items: list[dict], geom_wgs84: BaseGeometry) -> list[dict]:
    best: dict[str, dict] = {}
    for item in items:
        if not shape(item["geometry"]).contains(geom_wgs84):
            continue
        day = item["properties"]["datetime"][:10]
        current = best.get(day)
        if current is None or item["properties"]["eo:cloud_cover"] < current["properties"]["eo:cloud_cover"]:
            best[day] = item
    return list(best.values())


async def observe(
    item: dict, geom_2180: BaseGeometry, inner_buffer_m: float, light: bool = False
) -> tuple[SatelliteObservation | None, bool]:
    key = cache.make_key("s2obs-v2", item["id"], geom_2180.wkt, inner_buffer_m, light)
    cached = cache.get(key)
    if cached is not None:
        return (SatelliteObservation.model_validate(cached["obs"]) if cached["obs"] else None), cached["sharpened"]
    epsg = _epsg(item)
    geom = reproject(geom_2180, PL_CRS, epsg)
    inner = geom.buffer(-inner_buffer_m) if inner_buffer_m > 0 else geom
    if inner.is_empty or inner.area < 0.25 * geom.area:
        inner = geom
    assets = item["assets"]
    transform = asset_transform(assets["red"]) or await asyncio.to_thread(source_transform, assets["red"]["href"])
    grid = aligned_window(transform, geom.buffer(40).bounds, 2)
    w10 = Window(grid.col_off, grid.row_off, grid.width, grid.height)
    w20 = Window(grid.col_off // 2, grid.row_off // 2, grid.width // 2, grid.height // 2)
    names10 = LIGHT10 if light else tuple(BANDS10)
    names20 = LIGHT20 if light else tuple(BANDS20)
    keys = list(names10) + list(names20)
    tasks = [read_window_async(assets[BANDS10[k]]["href"], w10) for k in names10]
    tasks += [read_window_async(assets[BANDS20[k]]["href"], w20) for k in names20]
    raw = dict(zip(keys, await asyncio.gather(*tasks), strict=True))
    bands: dict[str, np.ndarray] = {}
    for band in keys:
        if band == "SCL":
            continue
        scale, offset = scale_offset(item, assets[BANDS10.get(band) or BANDS20[band]])
        data = raw[band].astype(np.float32)
        bands[band] = np.where(data > 0, data * scale + offset, np.nan)
    shape10 = bands["B04"].shape
    scl10 = np.repeat(np.repeat(raw["SCL"], 2, axis=0), 2, axis=1)[: shape10[0], : shape10[1]]
    valid = valid_mask(scl10, *[raw[k] for k in names10])
    predictors = [np.nan_to_num(bands[k], nan=0.0) for k in names10]
    sharpened = False
    for band in [b for b in names20 if b != "SCL"]:
        sharp, used = sharpen_band(np.nan_to_num(bands[band], nan=0.0), predictors, valid)
        bands[band] = np.where(sharp > 0, sharp, np.nan)
        sharpened |= used
    weights = coverage_weights(inner, grid.transform, shape10)
    indices = {
        "ndvi": normalized_difference(bands["B08"], bands["B04"]),
        "ndmi": normalized_difference(bands["B8A"], bands["B11"]),
    }
    if not light:
        indices["ndwi"] = normalized_difference(bands["B03"], bands["B08"])
        indices["ndre"] = normalized_difference(bands["B8A"], bands["B05"])
    stats = summarize(indices, weights, valid)
    observation = None
    if stats["effective_pixels"] >= 0.5:
        observation = SatelliteObservation(
            date=datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00")).date(),
            scene_id=item["id"],
            ndvi=_round(stats["ndvi"]),
            ndmi=_round(stats["ndmi"]),
            ndwi=_round(stats.get("ndwi")),
            ndre=_round(stats.get("ndre")),
            clear_fraction=round(stats["clear_fraction"], 2),
            effective_pixels=round(stats["effective_pixels"], 1),
        )
    cache.set(
        key, {"obs": observation.model_dump(mode="json") if observation else None, "sharpened": sharpened}, 365 * DAY
    )
    return observation, sharpened


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


async def _safe_observe(item, geom_2180, inner_buffer_m, light=False):
    try:
        return await observe(item, geom_2180, inner_buffer_m, light)
    except Exception:
        return None, False


async def latest(geom_2180: BaseGeometry, geom_wgs84: BaseGeometry, bbox, day: date, inner_buffer_m: float):
    items = _covering(await search(bbox, day - timedelta(days=40), day, 80), geom_wgs84)
    items.sort(key=lambda i: (i["properties"]["datetime"][:10], -i["properties"]["eo:cloud_cover"]), reverse=True)
    for start in range(0, min(len(items), 6), 2):
        results = await asyncio.gather(*[_safe_observe(i, geom_2180, inner_buffer_m) for i in items[start : start + 2]])
        sharpened = any(s for _, s in results)
        observations = sorted([o for o, _ in results if o is not None], key=lambda o: o.date, reverse=True)
        for observation in observations:
            if observation.clear_fraction >= 0.6:
                return observation, sharpened
    return None, False


async def same_window_history(
    geom_2180: BaseGeometry,
    geom_wgs84: BaseGeometry,
    bbox,
    day: date,
    years: int,
    inner_buffer_m: float,
    timeout_s: float,
    keep_running: bool = False,
):
    async def one_year(offset: int):
        try:
            target = day.replace(year=day.year - offset)
        except ValueError:
            target = day.replace(year=day.year - offset, day=28)
        if target - timedelta(days=12) >= SENTINEL2_START:
            items = _covering(
                await search(bbox, target - timedelta(days=12), target + timedelta(days=12), 40), geom_wgs84
            )
            items.sort(
                key=lambda i: (
                    i["properties"]["eo:cloud_cover"],
                    abs((date.fromisoformat(i["properties"]["datetime"][:10]) - target).days),
                )
            )
            for item in items[:2]:
                observation, _ = await _safe_observe(item, geom_2180, inner_buffer_m, light=True)
                if observation is not None and observation.clear_fraction >= 0.6:
                    return observation
        try:
            return await landsat.same_window(geom_2180, geom_wgs84, bbox, target)
        except Exception:
            return None

    results = await gather_within([one_year(k) for k in range(1, years + 1)], timeout_s, keep_running)
    return [r for r in results if isinstance(r, SatelliteObservation)]


async def season_points(
    geom_2180: BaseGeometry, geom_wgs84: BaseGeometry, bbox, day: date, inner_buffer_m: float, limit: int = 5
) -> list[tuple[date, float]]:
    items = _covering(await search(bbox, day - timedelta(days=120), day, 40), geom_wgs84)
    items.sort(key=lambda i: i["properties"]["datetime"], reverse=True)
    chosen: list[dict] = []
    for item in items:
        when = date.fromisoformat(item["properties"]["datetime"][:10])
        if all(abs((when - date.fromisoformat(c["properties"]["datetime"][:10])).days) >= 10 for c in chosen):
            chosen.append(item)
        if len(chosen) >= limit:
            break
    results = await asyncio.gather(*[_safe_observe(i, geom_2180, inner_buffer_m, light=True) for i in chosen])
    return sorted(
        (o.date, o.ndvi) for o, _ in results if o is not None and o.ndvi is not None and o.clear_fraction >= 0.6
    )
