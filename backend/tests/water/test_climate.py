from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.water.engine import climate_balance as cb
from app.water.engine.crops import get_crop
from app.water.engine.indices import climate_indicators, dry_spells, spi


def test_periods_match_regulation():
    ps = cb.periods(2024)
    assert len(ps) == 14
    assert (ps[0].start, ps[0].end) == (date(2024, 3, 21), date(2024, 5, 20))
    assert (ps[4].start, ps[4].end) == (date(2024, 5, 1), date(2024, 6, 30))
    assert (ps[-1].start, ps[-1].end) == (date(2024, 8, 1), date(2024, 9, 30))


def test_latest_complete_period():
    assert cb.latest_complete_period(date(2024, 3, 1)) is None
    assert cb.latest_complete_period(date(2024, 6, 25)).label == "21.04–20.06"


def test_threshold_lookup():
    assert cb.threshold("zboza_ozime", "I", 0) == -129.0
    assert cb.threshold("kukurydza_ziarno", "IV", 0) == "x"
    assert cb.threshold("burak_cukrowy", "I", 3) == "-"
    assert cb.threshold(None, "I", 0) is None


def test_spi_signs():
    hist = [60, 70, 80, 90, 100, 110, 75, 85, 95]
    assert spi(30, hist) < -1
    assert spi(150, hist) > 1
    assert spi(10, [1, 2]) is None


def test_dry_spells():
    s = pd.Series([0, 0, 5, 0, 0, 0, 0.2])
    assert dry_spells(s) == (4, 4)


def _frame(precip_scale=1.0):
    idx = [d.date() for d in pd.date_range("2014-01-01", "2024-09-30", freq="D")]
    rng = np.random.default_rng(5)
    doy = np.array([d.timetuple().tm_yday for d in idx])
    return pd.DataFrame(
        {
            "precip_mm": np.where(rng.random(len(idx)) < 0.35, 5.0, 0.0) * precip_scale,
            "et0_mm": 0.5 + 4 * np.sin(np.pi * (doy - 60) / 300).clip(0),
            "tmax_c": 15 + 15 * np.sin(np.pi * (doy - 60) / 300).clip(0),
        },
        index=pd.Index(idx, name="date"),
    )


def test_climate_indicators_dry_year_flagged():
    frame = _frame()
    frame.loc[[d for d in frame.index if d.year == 2024 and 4 <= d.month <= 7], "precip_mm"] = 0.0
    crop = get_crop("pszenica_ozima")
    years = list(range(2014, 2025))
    ci = climate_indicators(frame, date(2024, 7, 15), crop, "I", years, None)
    assert ci.kbw_drought is True
    assert ci.kbw_period_label == "11.05–10.07"
    assert ci.kbw_threshold_mm == -165.0
    assert ci.kbw_percentile == pytest.approx(0.0)
    assert 2024 in ci.seasons_with_kbw_drought
    assert ci.dry_spell_current_days > 60
    assert ci.spi_3 is not None and ci.spi_3 < -1.0
    assert len(ci.risk_calendar) == 18
