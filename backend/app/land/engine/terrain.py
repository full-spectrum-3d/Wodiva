from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
from rasterio import Affine
from rasterio.features import rasterize, shapes
from scipy.ndimage import label
from shapely.geometry import shape as to_shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass
class FloodResult:
    filled: np.ndarray
    parent: np.ndarray
    order: np.ndarray


@dataclass
class TerrainAnalysis:
    slope_pct: np.ndarray
    depth: np.ndarray
    accumulation_m2: np.ndarray
    twi: np.ndarray
    parcel_mask: np.ndarray
    depression_mask: np.ndarray
    channel_mask: np.ndarray
    mean_slope_pct: float
    p95_slope_pct: float
    twi_mean: float
    depression_area_m2: float
    depression_volume_m3: float
    flow_path_length_m: float
    outflow_share: float
    depressions: list[dict]
    channels: list[dict]


def priority_flood(dem: np.ndarray, valid: np.ndarray | None = None) -> FloodResult:
    h, w = dem.shape
    valid = np.isfinite(dem) if valid is None else valid & np.isfinite(dem)
    filled = np.where(valid, dem, np.nan).astype(np.float64)
    parent = np.full(h * w, -1, dtype=np.int64)
    closed = ~valid.copy()
    order = np.empty(int(valid.sum()), dtype=np.int64)
    heap: list[tuple[float, int, int]] = []
    counter = 0
    for r in range(h):
        for c in range(w):
            if closed[r, c]:
                continue
            edge = r == 0 or c == 0 or r == h - 1 or c == w - 1
            if not edge:
                for dr, dc in NEIGHBORS:
                    if not valid[r + dr, c + dc]:
                        edge = True
                        break
            if edge:
                closed[r, c] = True
                heapq.heappush(heap, (filled[r, c], counter, r * w + c))
                counter += 1
    n = 0
    while heap:
        z, _, idx = heapq.heappop(heap)
        order[n] = idx
        n += 1
        r, c = divmod(idx, w)
        for dr, dc in NEIGHBORS:
            rr, cc = r + dr, c + dc
            if rr < 0 or cc < 0 or rr >= h or cc >= w or closed[rr, cc]:
                continue
            closed[rr, cc] = True
            nz = filled[rr, cc]
            if nz < z:
                nz = z
                filled[rr, cc] = z
            parent[rr * w + cc] = idx
            heapq.heappush(heap, (nz, counter, rr * w + cc))
            counter += 1
    return FloodResult(filled=filled, parent=parent, order=order[:n])


def accumulation(flood: FloodResult, shape: tuple[int, int]) -> np.ndarray:
    acc = np.ones(shape[0] * shape[1], dtype=np.float64)
    parent = flood.parent
    for idx in flood.order[::-1]:
        p = parent[idx]
        if p >= 0:
            acc[p] += acc[idx]
    return acc.reshape(shape)


def slope_percent(dem: np.ndarray, res: float) -> np.ndarray:
    gy, gx = np.gradient(np.nan_to_num(dem, nan=float(np.nanmean(dem))), res)
    return np.hypot(gx, gy) * 100.0


def analyze(
    dem: np.ndarray,
    transform: Affine,
    parcel: BaseGeometry,
    depth_threshold_m: float,
    min_depression_m2: float,
    channel_area_m2: float,
) -> TerrainAnalysis:
    res = abs(transform.a)
    cell = res * res
    h, w = dem.shape
    parcel_mask = rasterize([(parcel, 1)], out_shape=(h, w), transform=transform, fill=0, dtype="uint8").astype(bool)
    if not parcel_mask.any():
        parcel_mask = rasterize(
            [(parcel, 1)], out_shape=(h, w), transform=transform, fill=0, dtype="uint8", all_touched=True
        ).astype(bool)
    flood = priority_flood(dem)
    depth = np.nan_to_num(flood.filled - dem, nan=0.0)
    acc_cells = accumulation(flood, (h, w))
    acc_m2 = acc_cells * cell
    slope = slope_percent(dem, res)
    tan_b = np.maximum(slope / 100.0, 0.001)
    twi = np.log((acc_cells * res) / tan_b)

    depression_mask = depth > depth_threshold_m
    labelled, count = label(depression_mask)
    near = rasterize(
        [(parcel.buffer(2 * res), 1)], out_shape=(h, w), transform=transform, fill=0, dtype="uint8"
    ).astype(bool)
    depressions = []
    keep = np.zeros_like(depression_mask)
    for lab in range(1, count + 1):
        region = labelled == lab
        if not (region & near).any():
            continue
        area = float(region.sum() * cell)
        if area < min_depression_m2:
            continue
        keep |= region
        geoms = [to_shape(g) for g, v in shapes(region.astype(np.uint8), mask=region, transform=transform) if v == 1]
        depressions.append(
            {
                "geometry": unary_union(geoms),
                "area_m2": round(area),
                "max_depth_m": round(float(depth[region].max()), 2),
                "volume_m3": round(float(depth[region].sum() * cell)),
                "inside_parcel_share": round(float((region & parcel_mask).sum() / region.sum()), 2),
            }
        )
    depressions.sort(key=lambda d: d["volume_m3"], reverse=True)

    channel_mask = (acc_m2 >= channel_area_m2) & near
    channels = []
    if channel_mask.any():
        labelled_c, count_c = label(channel_mask, structure=np.ones((3, 3)))
        for lab in range(1, count_c + 1):
            region = labelled_c == lab
            geoms = [
                to_shape(g) for g, v in shapes(region.astype(np.uint8), mask=region, transform=transform) if v == 1
            ]
            channels.append(
                {
                    "geometry": unary_union(geoms),
                    "length_m": round(float(region.sum() * res)),
                    "max_contributing_area_ha": round(float(acc_m2[region].max() / 1e4), 2),
                }
            )
        channels.sort(key=lambda c: c["max_contributing_area_ha"], reverse=True)

    in_dep = keep & parcel_mask
    terminal = np.zeros(h * w, dtype=bool)
    flat_dep = in_dep.ravel()
    parent = flood.parent
    for idx in flood.order:
        p = parent[idx]
        terminal[idx] = flat_dep[idx] or (p >= 0 and terminal[p])
    terminal = terminal.reshape(h, w)
    parcel_cells = int(parcel_mask.sum())
    outflow_share = float((parcel_mask & ~terminal).sum() / parcel_cells) if parcel_cells else 1.0

    return TerrainAnalysis(
        slope_pct=slope,
        depth=depth,
        accumulation_m2=acc_m2,
        twi=twi,
        parcel_mask=parcel_mask,
        depression_mask=keep,
        channel_mask=channel_mask,
        mean_slope_pct=round(float(slope[parcel_mask].mean()), 2) if parcel_cells else 0.0,
        p95_slope_pct=round(float(np.percentile(slope[parcel_mask], 95)), 2) if parcel_cells else 0.0,
        twi_mean=round(float(twi[parcel_mask].mean()), 2) if parcel_cells else 0.0,
        depression_area_m2=round(float((keep & parcel_mask).sum() * cell)),
        depression_volume_m3=round(float(depth[keep & parcel_mask].sum() * cell)),
        flow_path_length_m=round(float((channel_mask & parcel_mask).sum() * res)),
        outflow_share=round(outflow_share, 2),
        depressions=depressions[:6],
        channels=channels[:6],
    )


def runoff_risk(mean_slope_pct: float, flow_path_length_m: float) -> str:
    if mean_slope_pct >= 5 or (mean_slope_pct >= 3 and flow_path_length_m >= 100):
        return "wysoka"
    if mean_slope_pct >= 2 or flow_path_length_m >= 100:
        return "średnia"
    return "niska"
