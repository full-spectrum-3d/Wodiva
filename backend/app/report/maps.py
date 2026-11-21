from __future__ import annotations

import io
import threading

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource, ListedColormap
from matplotlib.patches import Patch
from shapely.geometry.base import BaseGeometry

from app.land.collect import LandArtifacts

LAYER_STYLE = {
    "trees": ("#3f8f3f", 0.45, "zadrzewienia (BDOT10k)"),
    "wetland": ("#4aa3a3", 0.6, "mokradła (BDOT10k)"),
    "water": ("#5fa8e8", 0.8, "wody (BDOT10k)"),
    "watercourse": ("#1f4fa8", 1.0, "cieki (BDOT10k)"),
    "ditch": ("#2f7fd8", 1.0, "rowy melioracyjne (BDOT10k)"),
}


def _extent(transform, shape) -> tuple[float, float, float, float]:
    h, w = shape
    return transform.c, transform.c + transform.a * w, transform.f + transform.e * h, transform.f


def _outline(ax, geom: BaseGeometry, **kwargs) -> None:
    geoms = getattr(geom, "geoms", [geom])
    for g in geoms:
        if g.geom_type == "Polygon":
            x, y = g.exterior.xy
            ax.plot(x, y, **kwargs)


# pyplot trzyma stan globalny i nie jest bezpieczny wątkowo, a render idzie w asyncio.to_thread
_PLOT_LOCK = threading.Lock()


def render(parcel_2180: BaseGeometry, artifacts: LandArtifacts | None) -> bytes:
    with _PLOT_LOCK:
        return _render(parcel_2180, artifacts)


def _render(parcel_2180: BaseGeometry, artifacts: LandArtifacts | None) -> bytes:
    artifacts = artifacts or LandArtifacts()
    fig, ax = plt.subplots(figsize=(7, 7), dpi=130)
    handles = []
    if artifacts.dem is not None:
        data = artifacts.dem.data
        shade = LightSource(azdeg=315, altdeg=45).hillshade(
            np.nan_to_num(data, nan=float(np.nanmean(data))),
            vert_exag=3,
            dx=artifacts.dem.resolution_m,
            dy=artifacts.dem.resolution_m,
        )
        ax.imshow(
            shade,
            cmap="gray",
            extent=_extent(artifacts.dem.transform, data.shape),
            alpha=0.55,
            interpolation="bilinear",
        )
    if artifacts.hydro is not None:
        extent = (
            _extent(artifacts.hydro.transform, next(iter(artifacts.hydro.masks.values())).shape)
            if artifacts.hydro.masks
            else None
        )
        for key, (color, alpha, label) in LAYER_STYLE.items():
            mask = artifacts.hydro.masks.get(key)
            if mask is None or not mask.any():
                continue
            ax.imshow(
                np.ma.masked_where(~mask, mask),
                cmap=ListedColormap([color]),
                extent=extent,
                alpha=alpha,
                interpolation="nearest",
            )
            handles.append(Patch(color=color, alpha=alpha, label=label))
    if artifacts.terrain is not None and artifacts.dem is not None:
        t = artifacts.terrain
        extent = _extent(artifacts.dem.transform, t.depth.shape)
        if t.depression_mask.any():
            ax.imshow(
                np.ma.masked_where(~t.depression_mask, t.depth),
                cmap="Blues",
                extent=extent,
                alpha=0.75,
                interpolation="nearest",
            )
            handles.append(Patch(color="#2b6cb0", label="zagłębienia terenu (zatrzymanie wody)"))
        if t.channel_mask.any():
            ax.imshow(
                np.ma.masked_where(~t.channel_mask, t.channel_mask),
                cmap=ListedColormap(["#e07a00"]),
                extent=extent,
                alpha=0.9,
                interpolation="nearest",
            )
            handles.append(Patch(color="#e07a00", label="linie spływu"))
    _outline(ax, parcel_2180, color="#d40000", linewidth=2.2)
    handles.append(Patch(facecolor="none", edgecolor="#d40000", linewidth=2, label="działka"))
    minx, miny, maxx, maxy = parcel_2180.buffer(max(120.0, (parcel_2180.area**0.5) * 0.4)).bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    span = maxx - minx
    bar = 10 ** int(np.floor(np.log10(span / 4)))
    bar = bar * 5 if span / bar > 15 else bar * 2 if span / bar > 7 else bar
    x0, y0 = minx + span * 0.05, miny + (maxy - miny) * 0.05
    ax.plot([x0, x0 + bar], [y0, y0], color="black", linewidth=3)
    ax.text(x0 + bar / 2, y0 + (maxy - miny) * 0.015, f"{bar:.0f} m", ha="center", fontsize=8)
    ax.legend(handles=handles, loc="upper right", fontsize=7, framealpha=0.85)
    ax.set_title("Działka: teren, spływ i obiekty wodne w otoczeniu", fontsize=10)
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    return buffer.getvalue()
