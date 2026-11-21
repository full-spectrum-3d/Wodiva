import csv
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from app.core.config import get_settings

PERIOD_STARTS = [
    (3, 21),
    (4, 1),
    (4, 11),
    (4, 21),
    (5, 1),
    (5, 11),
    (5, 21),
    (6, 1),
    (6, 11),
    (6, 21),
    (7, 1),
    (7, 11),
    (7, 21),
    (8, 1),
]


@dataclass(frozen=True)
class Period:
    index: int
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start:%d.%m}–{self.end:%d.%m}"


def _decade_end(d: date) -> date:
    if d.day <= 10:
        return d.replace(day=10)
    if d.day <= 20:
        return d.replace(day=20)
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def period(year: int, index: int) -> Period:
    m, d = PERIOD_STARTS[index]
    start = date(year, m, d)
    end = start
    for _ in range(6):
        end = _decade_end(end) + timedelta(days=1)
    return Period(index, start, end - timedelta(days=1))


def periods(year: int) -> list[Period]:
    return [period(year, i) for i in range(len(PERIOD_STARTS))]


def latest_complete_period(day: date) -> Period | None:
    done = [p for p in periods(day.year) if p.end <= day]
    return done[-1] if done else None


@lru_cache
def thresholds() -> dict[tuple[str, str], list[float | str]]:
    path = get_settings().data_dir / "water" / "kbw_thresholds.csv"
    out = {}
    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        for row in reader:
            values: list[float | str] = []
            for v in row[2:]:
                values.append(v if v in ("x", "-") else float(v))
            out[(row[0], row[1])] = values
    return out


def threshold(group: str | None, category: str | None, index: int) -> float | str | None:
    if not group or not category:
        return None
    values = thresholds().get((group, category))
    if values is None:
        return None
    return values[index]


def kbw_sum(frame: pd.DataFrame, start: date, end: date) -> float | None:
    window = frame[(frame.index >= start) & (frame.index <= end)]
    if len(window) < (end - start).days + 1 - 3:
        return None
    return float((window["precip_mm"] - window["et0_mm"]).sum())


def kbw_rolling(frame: pd.DataFrame, end: date, days: int = 60) -> float | None:
    return kbw_sum(frame, end - timedelta(days=days - 1), end)


def season_drought(frame: pd.DataFrame, year: int, group: str | None, category: str | None, until: date) -> bool | None:
    if not group or not category:
        return None
    flags = []
    for p in periods(year):
        if p.end > until:
            break
        t = threshold(group, category, p.index)
        if not isinstance(t, float):
            continue
        value = kbw_sum(frame, p.start, p.end)
        if value is not None:
            flags.append(value < t)
    if not flags:
        return None
    return any(flags)
