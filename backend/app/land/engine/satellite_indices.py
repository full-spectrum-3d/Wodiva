from __future__ import annotations

import numpy as np
from rasterio import Affine
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry

VALID_SCL = (4, 5, 6, 7)


def coverage_weights(geom: BaseGeometry, transform: Affine, shape: tuple[int, int], supersample: int = 5) -> np.ndarray:
    fine = transform @ Affine.scale(1 / supersample)
    h, w = shape
    mask = rasterize(
        [(geom, 1)],
        out_shape=(h * supersample, w * supersample),
        transform=fine,
        fill=0,
        dtype="uint8",
    )
    return mask.reshape(h, supersample, w, supersample).mean(axis=(1, 3)).astype(np.float32)


def normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / (a + b)
    out[~np.isfinite(out)] = np.nan
    return out


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float | None:
    ok = np.isfinite(values) & (weights > 0)
    total = float(weights[ok].sum())
    if total <= 0:
        return None
    return float((values[ok] * weights[ok]).sum() / total)


def valid_mask(scl10: np.ndarray, *bands: np.ndarray) -> np.ndarray:
    valid = np.isin(scl10, VALID_SCL)
    for band in bands:
        valid &= band > 0
    return valid


def summarize(indices: dict[str, np.ndarray], weights: np.ndarray, valid: np.ndarray) -> dict[str, float | None]:
    w = weights * valid
    total = float(weights.sum())
    out: dict[str, float | None] = {k: weighted_mean(v, w) for k, v in indices.items()}
    out["clear_fraction"] = float(w.sum() / total) if total > 0 else 0.0
    out["effective_pixels"] = float(w.sum())
    return out


def vci(current: float | None, history: list[float]) -> float | None:
    if current is None or len(history) < 3:
        return None
    values = [*history, current]
    low, high = min(values), max(values)
    if high - low < 0.05:
        return None
    return round((current - low) / (high - low), 2)
