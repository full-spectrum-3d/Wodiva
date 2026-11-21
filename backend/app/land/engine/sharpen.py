from __future__ import annotations

import numpy as np
from scipy.ndimage import zoom


def degrade(band10: np.ndarray) -> np.ndarray:
    h, w = band10.shape
    return band10[: h - h % 2, : w - w % 2].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))


def upsample(band20: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    up = zoom(band20, 2, order=1, mode="nearest", grid_mode=True)
    out = np.zeros(shape, dtype=np.float32)
    h = min(shape[0], up.shape[0])
    w = min(shape[1], up.shape[1])
    out[:h, :w] = up[:h, :w]
    return out


def sharpen_band(
    band20: np.ndarray, bands10: list[np.ndarray], valid10: np.ndarray | None = None
) -> tuple[np.ndarray, bool]:
    shape = bands10[0].shape
    plain = upsample(band20.astype(np.float32), shape)
    stack10 = np.stack([b.astype(np.float32) for b in bands10], axis=-1)
    stack20 = np.stack([degrade(b.astype(np.float32)) for b in bands10], axis=-1)
    h20 = min(band20.shape[0], stack20.shape[0])
    w20 = min(band20.shape[1], stack20.shape[1])
    y = band20[:h20, :w20].astype(np.float32).ravel()
    x = stack20[:h20, :w20].reshape(-1, stack20.shape[-1])
    ok = np.isfinite(y) & np.all(np.isfinite(x), axis=1) & (y > 0) & np.all(x > 0, axis=1)
    if valid10 is not None:
        ok &= degrade(valid10.astype(np.float32))[:h20, :w20].ravel() > 0.99
    if ok.sum() < max(12, stack20.shape[-1] * 4):
        return plain, False
    design = np.column_stack([np.ones(ok.sum()), x[ok]])
    coef, *_ = np.linalg.lstsq(design, y[ok], rcond=None)
    predicted10 = coef[0] + stack10 @ coef[1:]
    predicted20 = coef[0] + stack20[:h20, :w20] @ coef[1:]
    residual20 = np.zeros(band20.shape, dtype=np.float32)
    residual20[:h20, :w20] = band20[:h20, :w20] - predicted20
    sharp = predicted10 + upsample(residual20, shape)
    return sharp.astype(np.float32), True
