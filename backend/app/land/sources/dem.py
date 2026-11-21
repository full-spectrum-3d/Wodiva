from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.warp import reproject as warp
from shapely.geometry.base import BaseGeometry

from app.land.cache import DAY, cache
from app.land.geo import PL_CRS, reproject
from app.land.net import client
from app.land.settings import land_settings
from app.land.sources.cog import GDAL_ENV, semaphore

NMT_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModelFormatTIFF"
NMT_COVERAGE = "DTM_PL-KRON86-NH_TIFF"
COPDEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
MAX_CELLS = 160_000
NMT_TIMEOUT_S = 9.0


@dataclass
class Dem:
    data: np.ndarray
    transform: rasterio.Affine
    resolution_m: float
    source: str


def target_grid(bounds: tuple[float, float, float, float], min_res: float) -> tuple[rasterio.Affine, int, int, float]:
    minx, miny, maxx, maxy = bounds
    area = (maxx - minx) * (maxy - miny)
    res = max(min_res, math.sqrt(area / MAX_CELLS))
    res = math.ceil(res * 2) / 2
    width = max(8, math.ceil((maxx - minx) / res))
    height = max(8, math.ceil((maxy - miny) / res))
    transform = rasterio.Affine(res, 0, minx, 0, -res, maxy)
    return transform, width, height, res


def _resample(src_bytes_or_path, transform, width, height) -> np.ndarray:
    out = np.full((height, width), np.nan, dtype=np.float32)
    with rasterio.Env(**GDAL_ENV):
        if isinstance(src_bytes_or_path, (bytes, bytearray)):
            with MemoryFile(src_bytes_or_path) as memfile, memfile.open() as src:
                _warp_into(src, out, transform)
        else:
            with rasterio.open(src_bytes_or_path) as src:
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


async def _fetch_nmt(bounds) -> bytes | None:
    minx, miny, maxx, maxy = bounds
    variants = (
        [f"x({minx:.1f},{maxx:.1f})", f"y({miny:.1f},{maxy:.1f})"],
        [f"y({minx:.1f},{maxx:.1f})", f"x({miny:.1f},{maxy:.1f})"],
    )

    async def one(subsets):
        params = [
            ("SERVICE", "WCS"),
            ("VERSION", "2.0.1"),
            ("REQUEST", "GetCoverage"),
            ("COVERAGEID", NMT_COVERAGE),
            ("FORMAT", "image/tiff"),
        ]
        params += [("SUBSET", s) for s in subsets]
        response = await client().get(NMT_URL, params=params, timeout=NMT_TIMEOUT_S)
        if response.status_code == 200 and response.content[:2] in (b"II", b"MM"):
            return response.content
        raise ValueError("no coverage")

    tasks = [asyncio.create_task(one(v)) for v in variants]
    try:
        for finished in asyncio.as_completed(tasks):
            try:
                return await finished
            except Exception:
                continue
    finally:
        for task in tasks:
            task.cancel()
    return None


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
    nmt_transform, w1, h1, res1 = target_grid(bounds, 1.0)
    if cached is not None:
        meta = cache.get(key + ":meta")
        if meta is not None:
            data = np.frombuffer(cached, dtype=np.float32).reshape(meta["h"], meta["w"]).copy()
            return Dem(data, rasterio.Affine(*meta["t"]), meta["res"], meta["source"])
    nmt_task = asyncio.create_task(_fetch_nmt(bounds))
    cop_task = asyncio.create_task(_load_copdem(geom_2180, buffer_m, bounds))
    dem: Dem | None = None
    try:
        raw = await asyncio.wait_for(asyncio.shield(nmt_task), NMT_TIMEOUT_S)
    except Exception:
        raw = None
    if raw is not None:
        async with semaphore():
            data = await asyncio.to_thread(_resample, raw, nmt_transform, w1, h1)
        if np.isfinite(data).mean() > 0.9:
            dem = Dem(data, nmt_transform, res1, "nmt")
            cop_task.cancel()
    else:
        nmt_task.cancel()
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
