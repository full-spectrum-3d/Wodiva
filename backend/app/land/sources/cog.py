from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.windows import Window

from app.land.settings import land_settings

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_RETRY_DELAY": "0.5",
    "GDAL_HTTP_TIMEOUT": "25",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_VERSION": "2",
    "GDAL_INGESTED_BYTES_AT_OPEN": "32768",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
}

_semaphore: asyncio.Semaphore | None = None


def semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(land_settings().raster_concurrency)
    return _semaphore


@dataclass
class GridWindow:
    col_off: int
    row_off: int
    width: int
    height: int
    transform: rasterio.Affine


def source_transform(href: str) -> rasterio.Affine:
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        return src.transform


def asset_transform(asset: dict) -> rasterio.Affine | None:
    values = asset.get("proj:transform")
    if not values or len(values) < 6:
        return None
    return rasterio.Affine(*values[:6])


def aligned_window(t: rasterio.Affine, bounds: tuple[float, float, float, float], align: int = 2) -> GridWindow:
    minx, miny, maxx, maxy = bounds
    col0 = math.floor((minx - t.c) / t.a)
    row0 = math.floor((maxy - t.f) / t.e)
    col1 = math.ceil((maxx - t.c) / t.a)
    row1 = math.ceil((miny - t.f) / t.e)
    col0 -= col0 % align
    row0 -= row0 % align
    width = col1 - col0
    height = row1 - row0
    width += (-width) % align
    height += (-height) % align
    return GridWindow(col0, row0, max(width, align), max(height, align), t * rasterio.Affine.translation(col0, row0))


def read_window(href: str, window: Window) -> np.ndarray:
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        return src.read(1, window=window, boundless=True, fill_value=0)


async def read_window_async(href: str, window: Window) -> np.ndarray:
    async with semaphore():
        return await asyncio.to_thread(read_window, href, window)


_background: set[asyncio.Task] = set()


async def gather_within(coros, timeout_s: float, keep_running: bool = False) -> list:
    tasks = [asyncio.ensure_future(c) for c in coros]
    if not tasks:
        return []
    done, pending = await asyncio.wait(tasks, timeout=max(timeout_s, 0.1))
    for task in pending:
        if keep_running:
            _background.add(task)
            task.add_done_callback(_background.discard)
        else:
            task.cancel()
    return [t.result() for t in done if not t.cancelled() and t.exception() is None]
