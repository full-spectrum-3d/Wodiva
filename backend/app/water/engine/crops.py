import csv
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from app.core.config import get_settings


@dataclass(frozen=True)
class Crop:
    code: str
    name: str
    kbw_group: str | None
    sow: str
    ini_end: str
    dev_end: str
    mid_end: str
    harvest: str
    kc_ini: float
    kc_mid: float
    kc_end: float
    kc_off: float
    zr_min: float
    zr_max: float
    p: float
    critical_start: str
    critical_end: str
    critical_label: str
    perennial: bool


@dataclass(frozen=True)
class Season:
    year: int
    sow: date
    ini_end: date
    dev_end: date
    mid_end: date
    harvest: date

    def shifted(self, days: int) -> "Season":
        d = timedelta(days=days)
        return Season(self.year, self.sow, self.ini_end + d, self.dev_end + d, self.mid_end + d, self.harvest + d)

    def contains(self, day: date) -> bool:
        return self.sow <= day <= self.harvest


@lru_cache
def load_crops() -> dict[str, Crop]:
    path = get_settings().data_dir / "water" / "crops.csv"
    out = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["code"]] = Crop(
                code=r["code"],
                name=r["name"],
                kbw_group=r["kbw_group"] or None,
                sow=r["sow"],
                ini_end=r["ini_end"],
                dev_end=r["dev_end"],
                mid_end=r["mid_end"],
                harvest=r["harvest"],
                kc_ini=float(r["kc_ini"]),
                kc_mid=float(r["kc_mid"]),
                kc_end=float(r["kc_end"]),
                kc_off=float(r["kc_off"]),
                zr_min=float(r["zr_min"]),
                zr_max=float(r["zr_max"]),
                p=float(r["p"]),
                critical_start=r["critical_start"],
                critical_end=r["critical_end"],
                critical_label=r["critical_label"],
                perennial=r["perennial"] == "1",
            )
    return out


def get_crop(code: str) -> Crop:
    crops = load_crops()
    if code not in crops:
        raise KeyError(code)
    return crops[code]


def _md(year: int, md: str) -> date:
    month, day = (int(x) for x in md.split("-"))
    return date(year, month, day)


def season_for_year(crop: Crop, year: int) -> Season:
    harvest = _md(year, crop.harvest)
    dates = [harvest]
    for md in (crop.mid_end, crop.dev_end, crop.ini_end, crop.sow):
        candidate = _md(dates[-1].year, md)
        if candidate > dates[-1]:
            candidate = _md(dates[-1].year - 1, md)
        dates.append(candidate)
    harvest, mid_end, dev_end, ini_end, sow = dates
    return Season(year, sow, ini_end, dev_end, mid_end, harvest)


def seasons_between(crop: Crop, start: date, end: date) -> list[Season]:
    return [season_for_year(crop, y) for y in range(start.year, end.year + 2)]


def season_at(crop: Crop, day: date) -> Season | None:
    for year in (day.year, day.year + 1):
        s = season_for_year(crop, year)
        if s.contains(day):
            return s
    return None


def stage_of(season: Season | None, day: date) -> str:
    if season is None or not season.contains(day):
        return "poza sezonem"
    if day < season.ini_end:
        return "początkowa"
    if day < season.dev_end:
        return "rozwój"
    if day < season.mid_end:
        return "pełnia"
    return "dojrzewanie"


@dataclass
class CropCalendar:
    kc: np.ndarray
    zr: np.ndarray
    in_season: np.ndarray
    season_year: np.ndarray
    stage: list[str]


def calendar(
    crop: Crop,
    days: list[date],
    shift: tuple[int, int] | None = None,
    kc_evap_factor: float = 1.0,
) -> CropCalendar:
    n = len(days)
    kc = np.full(n, crop.kc_off * kc_evap_factor)
    zr = np.full(n, crop.zr_max)
    in_season = np.zeros(n, dtype=bool)
    season_year = np.zeros(n, dtype=int)
    stage = ["poza sezonem"] * n
    if n == 0:
        return CropCalendar(kc, zr, in_season, season_year, stage)
    index = {d: i for i, d in enumerate(days)}
    for season in seasons_between(crop, days[0], days[-1]):
        if shift and shift[0] == season.year:
            season = season.shifted(shift[1])
        d = max(season.sow, days[0])
        while d <= min(season.harvest, days[-1]):
            i = index.get(d)
            if i is not None:
                in_season[i] = True
                season_year[i] = season.year
                stage[i] = stage_of(season, d)
                kc[i] = _kc(crop, season, d, kc_evap_factor)
                zr[i] = _zr(crop, season, d)
            d += timedelta(days=1)
    return CropCalendar(kc, zr, in_season, season_year, stage)


def _frac(a: date, b: date, d: date) -> float:
    span = (b - a).days
    return 1.0 if span <= 0 else min(max((d - a).days / span, 0.0), 1.0)


def _kc(crop: Crop, s: Season, d: date, evap_factor: float) -> float:
    ini = crop.kc_ini * evap_factor
    if d < s.ini_end:
        return ini
    if d < s.dev_end:
        return ini + (crop.kc_mid - ini) * _frac(s.ini_end, s.dev_end, d)
    if d < s.mid_end:
        return crop.kc_mid
    return crop.kc_mid + (crop.kc_end - crop.kc_mid) * _frac(s.mid_end, s.harvest, d)


def _zr(crop: Crop, s: Season, d: date) -> float:
    if crop.perennial:
        return crop.zr_max
    return crop.zr_min + (crop.zr_max - crop.zr_min) * _frac(s.sow, s.dev_end, d)
