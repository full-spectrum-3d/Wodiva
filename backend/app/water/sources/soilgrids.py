import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import lru_cache

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from app.core.cache import get_cache
from app.core.http import SourceError, fetch, record_timing
from app.core.schemas import DataSource, SourceStatus

REST_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
VRT_URL = "/vsicurl/https://files.isric.org/soilgrids/latest/data/{prop}/{prop}_{depth}_mean.vrt"
PROPERTIES = ("sand", "clay", "soc")
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm")
FACTOR = {"sand": 10.0, "clay": 10.0, "silt": 10.0, "soc": 100.0}
REST_PAUSE_S = 1800
_pool = ThreadPoolExecutor(max_workers=15)
_rest_down_until = 0.0


def data_source(status: SourceStatus, note: str | None = None) -> DataSource:
    return DataSource(
        name="ISRIC SoilGrids 2.0 (250 m) – piasek, ił, węgiel organiczny 0–100 cm",
        url="https://docs.isric.org/globaldata/soilgrids/",
        license="CC BY 4.0",
        retrieved_at=datetime.now(UTC),
        status=status,
        note=note,
    )


def parse_rest(payload: dict) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for layer in payload.get("properties", {}).get("layers", []):
        prop = layer.get("name")
        factor = FACTOR.get(prop, 1.0)
        for depth in layer.get("depths", []):
            value = depth.get("values", {}).get("mean")
            if value is None:
                continue
            out.setdefault(depth["label"], {})[prop] = float(value) / float(factor)
    return out


GDAL_OPTIONS = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".vrt,.tif"}


@lru_cache
def _transformer(crs_wkt: str) -> Transformer:
    return Transformer.from_crs("EPSG:4326", crs_wkt, always_xy=True)


def _read_vrt(prop: str, depth: str, lat: float, lon: float) -> float | None:
    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(VRT_URL.format(prop=prop, depth=depth)) as ds:
        x, y = _transformer(ds.crs.to_wkt()).transform(lon, lat)
        row, col = ds.index(x, y)
        data = ds.read(1, window=Window(col - 1, row - 1, 3, 3), boundless=True, fill_value=ds.nodata or -32768)
        nodata = ds.nodata if ds.nodata is not None else -32768
        valid = data[data != nodata]
        if valid.size == 0:
            return None
        return float(np.mean(valid)) / FACTOR[prop]


async def _from_vrt(lat: float, lon: float) -> dict[str, dict[str, float]]:
    loop = asyncio.get_running_loop()
    jobs = {(p, d): loop.run_in_executor(_pool, _read_vrt, p, d, lat, lon) for p in PROPERTIES for d in DEPTHS}
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    out: dict[str, dict[str, float]] = {}
    for (prop, depth), value in zip(jobs.keys(), results, strict=True):
        if isinstance(value, float):
            out.setdefault(depth, {})[prop] = value
    return out


async def _from_rest(lat: float, lon: float) -> dict[str, dict[str, float]]:
    params = [("lon", f"{lon:.5f}"), ("lat", f"{lat:.5f}"), ("value", "mean")]
    params += [("property", p) for p in PROPERTIES] + [("depth", d) for d in DEPTHS]
    response = await fetch("soilgrids", REST_URL, params=params, retries=0, timeout=4)
    return parse_rest(response.json())


def _complete(layers: dict[str, dict[str, float]]) -> bool:
    return all(d in layers and all(p in layers[d] for p in PROPERTIES) for d in DEPTHS)


async def query(lat: float, lon: float) -> tuple[dict[str, dict[str, float]] | None, DataSource]:
    key = (round(lat, 3), round(lon, 3))
    cached = get_cache().get(get_cache().key("soilgrids", *key))
    if cached:
        return cached, data_source(SourceStatus.ok, "z pamięci podręcznej")
    global _rest_down_until
    layers: dict[str, dict[str, float]] = {}
    note = None
    if time.monotonic() >= _rest_down_until:
        try:
            layers = await _from_rest(lat, lon)
        except (SourceError, ValueError) as exc:
            _rest_down_until = time.monotonic() + REST_PAUSE_S
            note = f"REST niedostępne ({exc}); odczyt z plików VRT"
    else:
        note = "REST wstrzymane po wcześniejszym błędzie; odczyt z plików VRT"
    if not _complete(layers):
        started = time.perf_counter()
        try:
            vrt = await asyncio.wait_for(_from_vrt(lat, lon), timeout=20)
            for depth, values in vrt.items():
                layers.setdefault(depth, {}).update({k: v for k, v in values.items() if k not in layers[depth]})
        except TimeoutError:
            note = (note or "") + " VRT: przekroczony czas"
        finally:
            record_timing("soilgrids_vrt", time.perf_counter() - started)
    if not layers:
        return None, data_source(SourceStatus.missing, note or "brak danych SoilGrids")
    status = SourceStatus.ok if _complete(layers) else SourceStatus.partial
    if status == SourceStatus.ok:
        get_cache().set(get_cache().key("soilgrids", *key), layers, "soilgrids")
    return layers, data_source(status, note)
