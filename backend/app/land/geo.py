from functools import lru_cache

import numpy as np
import shapely
from pyproj import Transformer
from shapely import wkt
from shapely.geometry.base import BaseGeometry

PL_CRS = 2180


@lru_cache(maxsize=32)
def transformer(src: int | str, dst: int | str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def reproject(geom: BaseGeometry, src: int | str, dst: int | str) -> BaseGeometry:
    if src == dst:
        return geom
    t = transformer(src, dst)
    return shapely.transform(geom, lambda xy: np.column_stack(t.transform(xy[:, 0], xy[:, 1])))


def parcel_geometry(geometry_wkt_2180: str) -> BaseGeometry:
    return wkt.loads(geometry_wkt_2180)
