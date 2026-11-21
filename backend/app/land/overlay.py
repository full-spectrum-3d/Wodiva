import base64
import io
from dataclasses import dataclass

import matplotlib.image as mpimg
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from rasterio.features import rasterize
from rasterio.warp import Resampling, calculate_default_transform
from rasterio.warp import reproject as warp
from shapely.geometry.base import BaseGeometry

OPACITY = 0.75


@dataclass(frozen=True)
class Spec:
    label: str
    description: str
    unit: str
    value_range: tuple[float, float]
    colors: tuple[str, ...]
    classes: tuple[float, ...] = ()
    hide_below: float | None = None


SATELLITE = ("ndvi", "ndmi", "ndwi", "ndre")
TERRAIN = ("slope", "twi")

SPECS = {
    "ndvi": Spec(
        "NDVI",
        "Zieleń i kondycja roślin: brązowy to goła gleba lub słabe rośliny, zielony to bujne rośliny.",
        "",
        (0.0, 0.9),
        ("#8C510A", "#DFC27D", "#F6E8C3", "#A6DBA0", "#1B7837"),
    ),
    "ndmi": Spec(
        "NDMI",
        "Wilgotność roślin: czerwony to rośliny przesuszone, niebieski to dobrze uwodnione.",
        "",
        (-0.2, 0.4),
        ("#B2182B", "#F7F7F7", "#2166AC"),
    ),
    "ndwi": Spec(
        "NDWI",
        "Woda na powierzchni: niebieskie miejsca to zastoiska lub podtopienia.",
        "",
        (0.0, 0.3),
        ("#92C5DE", "#08306B"),
        hide_below=0.0,
    ),
    "ndre": Spec(
        "NDRE",
        "Stres roślin widoczny wcześniej niż w NDVI: brązowy to rośliny osłabione.",
        "",
        (0.0, 0.5),
        ("#8C510A", "#F6E8C3", "#01665E"),
    ),
    "slope": Spec(
        "Spadek terenu",
        "Gdzie woda najszybciej spływa: czerwony to strome miejsca, gdzie przydadzą się pasy buforowe.",
        "%",
        (0.0, 10.0),
        ("#FFFFCC", "#FED976", "#FD8D3C", "#BD0026"),
        classes=(2.0, 5.0, 10.0),
    ),
    "twi": Spec(
        "Wilgotność terenu (TWI)",
        "Gdzie woda się zbiera: ciemnoniebieski to miejsca najczęściej mokre.",
        "",
        (4.0, 14.0),
        ("#F7FBFF", "#08519C"),
    ),
}


def _colorize(name: str, values: np.ndarray) -> np.ndarray:
    spec = SPECS[name]
    finite = np.isfinite(values)
    if spec.classes:
        palette = np.array([to_rgba(c) for c in spec.colors])
        rgba = palette[np.digitize(np.nan_to_num(values, nan=0.0), spec.classes)]
    else:
        low, high = spec.value_range
        cmap = LinearSegmentedColormap.from_list(name, spec.colors)
        rgba = cmap(np.clip((np.nan_to_num(values, nan=low) - low) / (high - low), 0, 1))
    visible = finite if spec.hide_below is None else finite & (values > spec.hide_below)
    rgba[..., 3] = np.where(visible, OPACITY, 0.0)
    return rgba


def render(name: str, values: np.ndarray, transform: rasterio.Affine, crs: int, geom: BaseGeometry) -> dict | None:
    inside = rasterize(
        [(geom, 1)], out_shape=values.shape, transform=transform, fill=0, dtype="uint8", all_touched=True
    ).astype(bool)
    data = np.where(inside & np.isfinite(values), values, np.nan).astype(np.float32)
    if not np.isfinite(data).any():
        return None
    height, width = data.shape
    left, top = transform.c, transform.f
    right, bottom = left + width * transform.a, top + height * transform.e
    src_crs = f"EPSG:{crs}"
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
    buffer = io.BytesIO()
    mpimg.imsave(buffer, _colorize(name, out), format="png")
    west, north = dst_transform.c, dst_transform.f
    east, south = west + dst_w * dst_transform.a, north + dst_h * dst_transform.e
    return {"png": buffer.getvalue(), "bounds": [[round(south, 7), round(west, 7)], [round(north, 7), round(east, 7)]]}


def ndvi_overlay(ndvi: np.ndarray, transform: rasterio.Affine, epsg: int, geom: BaseGeometry) -> dict | None:
    return render("ndvi", ndvi, transform, epsg, geom)


def to_cache(overlay: dict) -> dict:
    return {"png": base64.b64encode(overlay["png"]).decode(), "bounds": overlay["bounds"]}


def from_cache(value: dict | None) -> dict | None:
    if not value:
        return None
    return {"png": base64.b64decode(value["png"]), "bounds": value["bounds"]}


def legend(name: str = "ndvi") -> dict:
    spec = SPECS[name]
    info = {
        "index": spec.label,
        "label": spec.label,
        "description": spec.description,
        "unit": spec.unit,
        "range": list(spec.value_range),
        "colors": list(spec.colors),
        "opacity": OPACITY,
    }
    if spec.classes:
        info["classes"] = list(spec.classes)
    if spec.hide_below is not None:
        info["hidden_below"] = spec.hide_below
    return info
