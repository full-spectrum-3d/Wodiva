from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from app.land.settings import data_dir

PHASE_LABELS = {
    "before_sowing": "przed siewem",
    "emergence": "wschody",
    "vegetative": "rozwój wegetatywny",
    "peak": "pełnia wegetacji",
    "ripening": "dojrzewanie",
    "after_harvest": "po zbiorze",
    "dormancy": "spoczynek zimowy",
}

INTERPRETABLE = {"vegetative", "peak"}
GREEN_PHASES = {"vegetative", "peak", "ripening"}


@dataclass(frozen=True)
class CropCalendar:
    crop: str
    stages: tuple[tuple[int, str], ...]
    ndvi_peak_typical: float


@lru_cache(maxsize=1)
def calendars() -> dict[str, CropCalendar]:
    out = {}
    with open(data_dir() / "phenology.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stages = tuple((int(doy), phase) for doy, phase in (item.split(":") for item in row["stages"].split(";")))
            out[row["crop"]] = CropCalendar(row["crop"], stages, float(row["ndvi_peak_typical"]))
    return out


def phase_on(crop: str, day: date) -> str:
    calendar = calendars()[crop]
    doy = day.timetuple().tm_yday
    current = calendar.stages[-1][1]
    for start, phase in calendar.stages:
        if doy >= start:
            current = phase
    return current


def is_interpretable(phase: str) -> bool:
    return phase in INTERPRETABLE


def anomaly_class(vci_values: list[float]) -> str | None:
    if not vci_values:
        return None
    value = min(vci_values)
    if value < 0.2:
        return "silnie poniżej normy"
    if value < 0.35:
        return "poniżej normy"
    if value < 0.65:
        return "w normie"
    return "powyżej normy"


BASE_NDVI = {"before_sowing": 0.2, "after_harvest": 0.25, "dormancy": 0.35, "emergence": 0.3}


def expected_ndvi(crop: str, doy: int) -> float:
    calendar = calendars()[crop]
    stages = list(calendar.stages)
    starts = [s for s, _ in stages] + [366]
    for i, (start, phase) in enumerate(stages):
        end = starts[i + 1]
        if start <= doy < end:
            t = (doy - start) / max(end - start, 1)
            if phase == "vegetative":
                return 0.3 + (calendar.ndvi_peak_typical - 0.3) * t
            if phase == "peak":
                return calendar.ndvi_peak_typical
            if phase == "ripening":
                return calendar.ndvi_peak_typical - (calendar.ndvi_peak_typical - 0.3) * t
            return BASE_NDVI[phase]
    return BASE_NDVI.get(stages[-1][1], 0.3)


def phase_offset(crop: str, points: list[tuple[int, float]], max_shift: int = 30) -> int | None:
    if len(points) < 3:
        return None
    values = [v for _, v in points]
    if max(values) - min(values) < 0.15:
        return None

    def error(shift: int) -> float:
        return sum((v - expected_ndvi(crop, max(1, min(365, doy - shift)))) ** 2 for doy, v in points)

    errors = {shift: error(shift) for shift in range(-max_shift, max_shift + 1, 2)}
    best = min(errors, key=errors.get)
    if best == 0 or errors[0] - errors[best] < 0.02 or abs(best) == max_shift:
        return 0 if best == 0 else None
    return best
