from functools import lru_cache

import numpy as np
import shapely
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry


@lru_cache
def to_2180() -> Transformer:
    return Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)


@lru_cache
def to_4326() -> Transformer:
    return Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)


def lonlat_to_2180(lon: float, lat: float) -> tuple[float, float]:
    return to_2180().transform(lon, lat)


def reproject(geom: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    return shapely.transform(geom, lambda c: np.column_stack(transformer.transform(c[:, 0], c[:, 1])))


def geom_to_4326(geom: BaseGeometry) -> BaseGeometry:
    return reproject(geom, to_4326())


def parse_wkt(text: str) -> BaseGeometry:
    if text.upper().startswith("SRID="):
        text = text.split(";", 1)[1]
    geom = wkt.loads(text)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def geojson_4326(geom_2180: BaseGeometry) -> dict:
    return mapping(geom_to_4326(geom_2180))


def count_parts(geom: BaseGeometry) -> int:
    return len(getattr(geom, "geoms", [geom]))
