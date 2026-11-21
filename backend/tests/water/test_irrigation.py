from datetime import date, timedelta

import numpy as np
import pandas as pd
from shapely.geometry import box

from app.water.engine.crops import get_crop
from app.water.engine.soil_water import simulate
from app.water.irrigation import advise
from app.water.parcel import build_parcel
from app.water.soil import layers_from_category


def _parcel(agri=True):
    p = build_parcel({"id": "t", "geom_wkt": box(745000, 370000, 745100, 370100).wkt}, "test")
    p.is_agricultural = agri
    return p


def _sim(precip_scale: float, crop="ziemniak"):
    days = [d.date() for d in pd.date_range("2023-01-01", "2024-07-15", freq="D")]
    p = np.full(len(days), 1.6 * precip_scale)
    e = np.full(len(days), 3.5)
    return simulate(days, p, e, get_crop(crop), layers_from_category("I"), 0.1), days


def _forecast(start: date, precip: float):
    idx = pd.Index([start + timedelta(days=k) for k in range(1, 8)], name="date")
    return pd.DataFrame({"precip_mm": [precip] * 7, "et0_mm": [4.0] * 7}, index=idx)


def test_dry_soil_recommends_irrigation_with_dose():
    sim, days = _sim(0.1)
    adv = advise(sim, get_crop("ziemniak"), _parcel(), days[-1], _forecast(days[-1], 0.0))
    assert adv.status == "zalecane"
    assert adv.net_dose_mm and adv.net_dose_mm > 0
    assert adv.volume_m3 == round(adv.gross_dose_mm * 1.0 * 10, 0)
    assert adv.forecast_available


def test_wet_soil_no_irrigation():
    sim, days = _sim(3.0)
    adv = advise(sim, get_crop("ziemniak"), _parcel(), days[-1], _forecast(days[-1], 10.0))
    assert adv.status in {"niezalecane", "monitoruj"}


def test_non_agricultural_and_off_season():
    sim, days = _sim(0.1)
    assert advise(sim, get_crop("ziemniak"), _parcel(False), days[-1], None).status == "nie dotyczy"
    jan = date(2024, 1, 15)
    assert advise(sim, get_crop("ziemniak"), _parcel(), jan, pd.DataFrame()).status == "nie dotyczy"


def test_historical_without_forecast():
    sim, days = _sim(0.1)
    adv = advise(sim, get_crop("ziemniak"), _parcel(), days[-1], pd.DataFrame(columns=["precip_mm", "et0_mm"]))
    assert adv.status == "zalecane" and adv.forecast_available is False


def test_no_irrigation_in_maturation_for_dry_harvest_crops():
    days = [d.date() for d in pd.date_range("2023-01-01", "2024-07-20", freq="D")]
    sim = simulate(
        days, np.full(len(days), 0.1), np.full(len(days), 3.5), get_crop("rzepak_ozimy"), layers_from_category("I"), 0.1
    )
    adv = advise(sim, get_crop("rzepak_ozimy"), _parcel(), date(2024, 7, 1), pd.DataFrame())
    assert adv.status == "niezalecane" and "dojrzewania" in adv.reason
