from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.water.engine.crops import get_crop, season_at, season_for_year, stage_of
from app.water.engine.scenarios import run_scenarios
from app.water.engine.soil_water import runoff_coefficient, simulate, state_at, stress_days_by_season
from app.water.soil import layers_from_category


def _days(start="2015-01-01", end="2024-12-31"):
    return [d.date() for d in pd.date_range(start, end, freq="D")]


def _weather(days, precip_mm=1.5, et0_mm=3.0, seed=3):
    rng = np.random.default_rng(seed)
    p = np.where(rng.random(len(days)) < 0.3, precip_mm / 0.3, 0.0)
    doy = np.array([d.timetuple().tm_yday for d in days])
    e = np.clip(et0_mm * (0.3 + 1.2 * np.sin(np.pi * (doy - 30) / 330).clip(0)), 0.2, None)
    return p, e


def test_mass_balance_constant_root_depth():
    days = _days()
    p, e = _weather(days)
    crop = get_crop("uzytki_zielone")
    layers = layers_from_category("III")
    sim = simulate(days, p, e, crop, layers, runoff_coef=0.1)
    inflow = p.sum() - sim.runoff.sum() - sim.deep_percolation.sum()
    outflow = sim.etc.sum()
    assert inflow - outflow == pytest.approx(-(sim.depletion[-1] - 0.0), abs=1e-6)


def test_depletion_within_bounds():
    days = _days()
    p, e = _weather(days, precip_mm=0.5, et0_mm=4.0)
    sim = simulate(days, p, e, get_crop("kukurydza_ziarno"), layers_from_category("I"), 0.1)
    assert np.all(sim.depletion >= 0)
    assert np.all(sim.depletion <= sim.taw + 1e-9)
    assert np.all((sim.ks >= 0) & (sim.ks <= 1))


def test_more_rain_less_stress():
    days = _days()
    crop = get_crop("pszenica_ozima")
    layers = layers_from_category("II")
    p, e = _weather(days, precip_mm=1.2)
    dry = simulate(days, p, e, crop, layers, 0.1)
    wet = simulate(days, p * 1.6, e, crop, layers, 0.1)
    assert sum(stress_days_by_season(wet).values()) < sum(stress_days_by_season(dry).values())


def test_heavier_soil_less_stress():
    days = _days()
    crop = get_crop("jeczmien_jary")
    p, e = _weather(days, precip_mm=1.3)
    light = simulate(days, p, e, crop, layers_from_category("I"), 0.1)
    heavy = simulate(days, p, e, crop, layers_from_category("IV"), 0.1)
    assert sum(stress_days_by_season(heavy).values()) <= sum(stress_days_by_season(light).values())


def test_winter_season_spans_years():
    crop = get_crop("pszenica_ozima")
    s = season_for_year(crop, 2024)
    assert s.sow == date(2023, 9, 25)
    assert s.harvest == date(2024, 7, 31)
    assert season_at(crop, date(2023, 11, 1)).year == 2024
    assert season_at(crop, date(2024, 8, 15)) is None
    assert stage_of(s, date(2024, 6, 1)) == "pełnia"


def test_phase_shift_moves_stages():
    days = _days("2023-01-01", "2024-12-31")
    p, e = _weather(days)
    crop = get_crop("kukurydza_ziarno")
    layers = layers_from_category("III")
    base = simulate(days, p, e, crop, layers, 0.1)
    late = simulate(days, p, e, crop, layers, 0.1, phase_shift=(2024, 14))
    i = days.index(date(2024, 6, 20))
    assert late.kc[i] < base.kc[i]


def test_state_and_scenarios():
    days = _days()
    p, e = _weather(days, precip_mm=1.0, et0_mm=4.0)
    crop = get_crop("ziemniak")
    layers = layers_from_category("I")
    coef = runoff_coefficient(6.0, "I")
    sim = simulate(days, p, e, crop, layers, coef)
    st = state_at(sim, date(2024, 7, 10))
    assert st.in_season and st.stage in {"pełnia", "rozwój"}
    assert 0 <= st.available_pct <= 100
    assert len(st.last_90_days) == 90
    results = run_scenarios(sim, p, e, crop, layers, coef, date(2024, 12, 31))
    assert {r.code for r in results} == {"mulcz", "prochnica", "splyw"}
    for r in results:
        assert r.stress_days_scenario <= r.stress_days_baseline


def test_runoff_grows_with_slope():
    assert runoff_coefficient(10, "III") > runoff_coefficient(1, "III")
    assert runoff_coefficient(None, None) > 0
