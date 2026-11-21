from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

from app.core.schemas import ClimateIndicators, DecadeRisk
from app.water.engine import climate_balance as cb
from app.water.engine.crops import Crop
from app.water.engine.soil_water import Simulation

MONTHS_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
HOT_DAY_C = 30.0
DRY_DAY_MM = 1.0


def same_date(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:
        return day.replace(year=year, day=28)


def window_sum(frame: pd.DataFrame, col: str, end: date, days: int) -> float | None:
    start = end - timedelta(days=days - 1)
    w = frame.loc[(frame.index >= start) & (frame.index <= end), col]
    if len(w) < days - 2:
        return None
    return float(w.sum())


def history_values(frame: pd.DataFrame, col: str, day: date, days: int, years: list[int]) -> list[float]:
    out = []
    for y in years:
        if y == day.year:
            continue
        v = window_sum(frame, col, same_date(day, y), days)
        if v is not None:
            out.append(v)
    return out


def spi(current: float | None, history: list[float]) -> float | None:
    if current is None or len(history) < 6:
        return None
    sample = np.array(history + [current])
    nonzero = sample[sample > 0]
    q = 1 - len(nonzero) / len(sample)
    if len(nonzero) < 4 or np.var(nonzero) == 0:
        return None
    shape, _, scale = stats.gamma.fit(nonzero, floc=0)
    prob = q + (1 - q) * (stats.gamma.cdf(current, shape, scale=scale) if current > 0 else 0)
    prob = float(np.clip(prob, 0.001, 0.999))
    return round(float(stats.norm.ppf(prob)), 2)


def dry_spells(precip: pd.Series) -> tuple[int, int]:
    current = longest = run = 0
    for v in precip.to_numpy():
        run = run + 1 if v < DRY_DAY_MM else 0
        longest = max(longest, run)
    current = run
    return current, longest


def decades(year: int) -> list[tuple[int, int, date, date]]:
    out = []
    for m in range(4, 10):
        for k, (a, b) in enumerate(((1, 10), (11, 20), (21, None))):
            start = date(year, m, a)
            end = date(year, m, b) if b else (date(year, m + 1, 1) - timedelta(days=1))
            out.append((m, k + 1, start, end))
    return out


def risk_calendar(
    frame: pd.DataFrame,
    sim: Simulation | None,
    crop: Crop,
    category: str | None,
    years: list[int],
    until: date,
) -> list[DecadeRisk]:
    stress = pd.Series(sim.stress, index=sim.days) if sim is not None else None
    out = []
    for m, k, _, _ in decades(2001):
        stress_hits, stress_n, kbw_hits, kbw_n = 0, 0, 0, 0
        for y in years:
            _, _, start, end = next(d for d in decades(y) if d[0] == m and d[1] == k)
            if end > until:
                continue
            if stress is not None:
                window = stress[(stress.index >= start) & (stress.index <= end)]
                if len(window):
                    stress_n += 1
                    stress_hits += int(window.mean() >= 0.5)
            idx = [p for p in cb.periods(y) if p.end == end]
            if idx:
                t = cb.threshold(crop.kbw_group, category, idx[0].index)
                v = cb.kbw_sum(frame, idx[0].start, idx[0].end)
                if isinstance(t, float) and v is not None:
                    kbw_n += 1
                    kbw_hits += int(v < t)
        out.append(
            DecadeRisk(
                month=m,
                decade=k,
                label=f"{k}. dekada {MONTHS_PL[m - 1]}",
                stress_freq=round(stress_hits / stress_n, 2) if stress_n else None,
                kbw_deficit_freq=round(kbw_hits / kbw_n, 2) if kbw_n else None,
            )
        )
    return out


def climate_indicators(
    frame: pd.DataFrame,
    day: date,
    crop: Crop,
    category: str | None,
    years: list[int],
    sim: Simulation | None,
) -> ClimateIndicators:
    kbw60 = cb.kbw_rolling(frame, day) or 0.0
    period = cb.latest_complete_period(day)
    kbw_period = cb.kbw_sum(frame, period.start, period.end) if period else None
    thr = cb.threshold(crop.kbw_group, category, period.index) if period else None
    thr_value = thr if isinstance(thr, float) else None
    drought = (kbw_period < thr_value) if (kbw_period is not None and thr_value is not None) else None
    hist_kbw = [v for y in years if y != day.year if (v := cb.kbw_rolling(frame, same_date(day, y))) is not None]
    percentile = round(100 * float(np.mean(np.array(hist_kbw) <= kbw60)), 0) if len(hist_kbw) >= 3 else None
    p30 = window_sum(frame, "precip_mm", day, 30) or 0.0
    p90 = window_sum(frame, "precip_mm", day, 90)
    p30_hist = history_values(frame, "precip_mm", day, 30, years)
    p90_hist = history_values(frame, "precip_mm", day, 90, years)
    e30 = window_sum(frame, "et0_mm", day, 30) or 0.0
    e30_hist = history_values(frame, "et0_mm", day, 30, years)
    e_norm = float(np.mean(e30_hist)) if e30_hist else None
    last30 = frame[(frame.index > day - timedelta(days=30)) & (frame.index <= day)]
    last90 = frame[(frame.index > day - timedelta(days=90)) & (frame.index <= day)]
    season_start = date(day.year, 4, 1)
    season = frame[(frame.index >= season_start) & (frame.index <= day)]
    current_dry, _ = dry_spells(last90["precip_mm"])
    _, max_dry = dry_spells(last90["precip_mm"])
    drought_years = [y for y in years if cb.season_drought(frame, y, crop.kbw_group, category, day)]
    return ClimateIndicators(
        kbw_60d_mm=round(kbw60, 1),
        kbw_period_label=period.label if period else None,
        kbw_period_mm=round(kbw_period, 1) if kbw_period is not None else None,
        kbw_threshold_mm=thr_value,
        kbw_drought=drought,
        kbw_percentile=percentile,
        spi_1=spi(p30, p30_hist),
        spi_3=spi(p90, p90_hist),
        precip_30d_mm=round(p30, 1),
        precip_30d_norm_mm=round(float(np.mean(p30_hist)), 1) if p30_hist else None,
        et0_30d_mm=round(e30, 1),
        et0_anomaly_pct=round((e30 - e_norm) / e_norm * 100, 1) if e_norm else None,
        hot_days_30d=int((last30["tmax_c"] >= HOT_DAY_C).sum()),
        hot_days_season=int((season["tmax_c"] >= HOT_DAY_C).sum()),
        dry_spell_current_days=current_dry,
        dry_spell_max_90d_days=max_dry,
        years_analyzed=years,
        seasons_with_kbw_drought=drought_years,
        risk_calendar=risk_calendar(frame, sim, crop, category, years, day),
    )
