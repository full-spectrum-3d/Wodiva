from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.core.schemas import SoilLayer, SoilWaterDay, SoilWaterState
from app.water.engine.crops import Crop, calendar

RUNOFF_THRESHOLD_MM = 8.0
SOIL_RUNOFF_FACTOR = {"I": 0.6, "II": 0.8, "III": 1.0, "IV": 1.2, None: 1.0}


@dataclass
class Modifiers:
    kc_evap_factor: float = 1.0
    runoff_factor: float = 1.0
    layers: list[SoilLayer] | None = None


@dataclass
class Simulation:
    days: list[date]
    depletion: np.ndarray
    taw: np.ndarray
    raw: np.ndarray
    ks: np.ndarray
    etc: np.ndarray
    precip: np.ndarray
    runoff: np.ndarray
    deep_percolation: np.ndarray
    in_season: np.ndarray
    season_year: np.ndarray
    stage: list[str]
    zr: np.ndarray
    kc: np.ndarray
    notes: list[str] = field(default_factory=list)

    @property
    def available_pct(self) -> np.ndarray:
        return np.where(self.taw > 0, 100 * (1 - self.depletion / self.taw), np.nan)

    @property
    def stress(self) -> np.ndarray:
        return self.in_season & (self.ks < 0.999)


def runoff_coefficient(slope_pct: float | None, soil_category: str | None) -> float:
    slope = 2.0 if slope_pct is None else max(slope_pct, 0.0)
    base = 0.05 + 0.025 * slope
    return float(np.clip(base * SOIL_RUNOFF_FACTOR.get(soil_category, 1.0), 0.03, 0.6))


def taw_profile(layers: list[SoilLayer], zr_m: float) -> float:
    depth_cm = zr_m * 100
    total = 0.0
    last = layers[-1]
    for layer in layers:
        top, bottom = layer.top_cm, layer.bottom_cm
        if depth_cm <= top:
            break
        total += layer.awc * (min(bottom, depth_cm) - top) * 10
    if depth_cm > last.bottom_cm:
        total += last.awc * (depth_cm - last.bottom_cm) * 10
    return total


def simulate(
    days: list[date],
    precip: np.ndarray,
    et0: np.ndarray,
    crop: Crop,
    layers: list[SoilLayer],
    runoff_coef: float,
    phase_shift: tuple[int, int] | None = None,
    mods: Modifiers | None = None,
) -> Simulation:
    mods = mods or Modifiers()
    layers = mods.layers or layers
    cal = calendar(crop, days, phase_shift, mods.kc_evap_factor)
    n = len(days)
    zr_unique = {float(z) for z in np.round(cal.zr, 3)}
    taw_cache = {z: taw_profile(layers, z) for z in zr_unique}
    coef = runoff_coef * mods.runoff_factor
    out = {k: np.zeros(n) for k in ("dr", "taw", "raw", "ks", "etc", "ro", "dp")}
    dr = 0.0
    taw_prev = None
    zr_prev = None
    for i in range(n):
        zr = float(np.round(cal.zr[i], 3))
        taw = taw_cache[zr]
        if taw_prev is not None and taw_prev > 0 and zr < zr_prev:
            dr = dr * taw / taw_prev
        dr = min(dr, taw)
        kc = cal.kc[i]
        e0 = max(float(et0[i]), 0.0)
        p_adj = float(np.clip(crop.p + 0.04 * (5 - kc * e0), 0.1, 0.8))
        raw = p_adj * taw
        p = max(float(precip[i]), 0.0)
        ro = coef * max(0.0, p - RUNOFF_THRESHOLD_MM)
        ks = 1.0 if dr <= raw or taw <= 0 else max(0.0, (taw - dr) / ((1 - p_adj) * taw))
        etc = ks * kc * e0
        new = dr - (p - ro) + etc
        dp = 0.0
        if new < 0:
            dp = -new
            new = 0.0
        dr = min(new, taw)
        out["dr"][i], out["taw"][i], out["raw"][i], out["ks"][i] = dr, taw, raw, ks
        out["etc"][i], out["ro"][i], out["dp"][i] = etc, ro, dp
        taw_prev, zr_prev = taw, zr
    return Simulation(
        days=days,
        depletion=out["dr"],
        taw=out["taw"],
        raw=out["raw"],
        ks=out["ks"],
        etc=out["etc"],
        precip=np.asarray(precip, dtype=float),
        runoff=out["ro"],
        deep_percolation=out["dp"],
        in_season=cal.in_season,
        season_year=cal.season_year,
        stage=cal.stage,
        zr=cal.zr,
        kc=cal.kc,
    )


def stress_days_by_season(sim: Simulation, until: date | None = None) -> dict[int, int]:
    mask = sim.stress.copy()
    if until is not None:
        mask &= np.array([d <= until for d in sim.days])
    years = sim.season_year[mask]
    out = {int(y): int((years == y).sum()) for y in np.unique(sim.season_year[sim.in_season])}
    return out


def percentile_same_date(sim: Simulation, day: date, window: int = 3) -> float | None:
    values = sim.available_pct
    index = {d: i for i, d in enumerate(sim.days)}
    if day not in index:
        return None
    current = values[index[day]]
    others = []
    for year in sorted({d.year for d in sim.days}):
        if year == day.year:
            continue
        try:
            ref = day.replace(year=year)
        except ValueError:
            ref = day.replace(year=year, day=28)
        idx = [
            index[d] for d in (ref.fromordinal(ref.toordinal() + k) for k in range(-window, window + 1)) if d in index
        ]
        if len(idx) == 2 * window + 1:
            others.append(float(np.mean(values[idx])))
    if len(others) < 3:
        return None
    return round(100 * float(np.mean(np.array(others) <= current)), 0)


def state_at(sim: Simulation, day: date, history_years: int = 10) -> SoilWaterState:
    index = {d: i for i, d in enumerate(sim.days)}
    i = index[day]
    current_season = int(sim.season_year[i]) if sim.in_season[i] else None
    by_year = stress_days_by_season(sim, until=day)
    season_stress = by_year.get(current_season, 0) if current_season else 0
    season_mask = (
        (sim.season_year == current_season) & np.array([d <= day for d in sim.days]) if current_season else None
    )
    runoff_season = float(sim.runoff[season_mask].sum()) if season_mask is not None else 0.0
    start = max(0, i - 89)
    last = [
        SoilWaterDay(
            date=sim.days[k],
            depletion_mm=round(float(sim.depletion[k]), 1),
            taw_mm=round(float(sim.taw[k]), 1),
            raw_mm=round(float(sim.raw[k]), 1),
            ks=round(float(sim.ks[k]), 3),
            precip_mm=round(float(sim.precip[k]), 1),
            etc_mm=round(float(sim.etc[k]), 2),
            in_season=bool(sim.in_season[k]),
        )
        for k in range(start, i + 1)
    ]
    min_year = day.year - history_years
    return SoilWaterState(
        date=day,
        in_season=bool(sim.in_season[i]),
        stage=sim.stage[i],
        root_depth_m=round(float(sim.zr[i]), 2),
        taw_mm=round(float(sim.taw[i]), 1),
        raw_mm=round(float(sim.raw[i]), 1),
        depletion_mm=round(float(sim.depletion[i]), 1),
        available_pct=round(float(sim.available_pct[i]), 1),
        ks=round(float(sim.ks[i]), 3),
        percentile_10y=percentile_same_date(sim, day),
        stress_days_season=season_stress,
        stress_days_by_year={y: v for y, v in by_year.items() if y >= min_year and y <= day.year + 1},
        runoff_season_mm=round(runoff_season, 1),
        last_90_days=last,
    )
