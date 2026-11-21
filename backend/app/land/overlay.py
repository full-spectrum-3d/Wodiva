import base64
import io

import matplotlib.image as mpimg
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from rasterio.features import rasterize
from rasterio.warp import Resampling, calculate_default_transform
from rasterio.warp import reproject as warp
from shapely.geometry.base import BaseGeometry

NDVI_COLORS = ["#8C510A", "#DFC27D", "#F6E8C3", "#A6DBA0", "#1B7837"]
NDVI_RANGE = (0.0, 0.9)
OPACITY = 0.75
_CMAP = LinearSegmentedColormap.from_list("ndvi", NDVI_COLORS)


def ndvi_overlay(ndvi: np.ndarray, transform: rasterio.Affine, epsg: int, geom: BaseGeometry) -> dict | None:
    inside = rasterize(
        [(geom, 1)], out_shape=ndvi.shape, transform=transform, fill=0, dtype="uint8", all_touched=True
    ).astype(bool)
    data = np.where(inside & np.isfinite(ndvi), ndvi, np.nan).astype(np.float32)
    if not np.isfinite(data).any():
        return None
    height, width = data.shape
    left, top = transform.c, transform.f
    right, bottom = left + width * transform.a, top + height * transform.e
    src_crs = f"EPSG:{epsg}"
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs, "EPSG:4326", width, height, left, bottom, right, top
    )
    out = np.full((dst_h, dst_w), np.nan, dtype=np.float32)
    warp(
        data,
        out,
        src_transform=transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs="EPSG:4326",
        resampling=Resampling.nearest,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    low, high = NDVI_RANGE
    rgba = _CMAP(np.clip((np.nan_to_num(out, nan=low) - low) / (high - low), 0, 1))
    rgba[..., 3] = np.where(np.isfinite(out), OPACITY, 0.0)
    buffer = io.BytesIO()
    mpimg.imsave(buffer, rgba, format="png")
    west, north = dst_transform.c, dst_transform.f
    east, south = west + dst_w * dst_transform.a, north + dst_h * dst_transform.e
    return {"png": buffer.getvalue(), "bounds": [[round(south, 7), round(west, 7)], [round(north, 7), round(east, 7)]]}


def to_cache(overlay: dict) -> dict:
    return {"png": base64.b64encode(overlay["png"]).decode(), "bounds": overlay["bounds"]}


def from_cache(value: dict | None) -> dict | None:
    if not value:
        return None
    return {"png": base64.b64decode(value["png"]), "bounds": value["bounds"]}


def legend() -> dict:
    return {"index": "NDVI", "range": list(NDVI_RANGE), "colors": NDVI_COLORS, "opacity": OPACITY}
