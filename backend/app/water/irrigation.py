from datetime import date

import numpy as np
import pandas as pd

from app.core.schemas import IrrigationAdvice, Parcel
from app.water.engine.crops import Crop, calendar
from app.water.engine.soil_water import Simulation

APPLICATION_EFFICIENCY = 0.75
MAX_SINGLE_DOSE_MM = 30.0
WINTER_MONTHS = {11, 12, 1, 2}
DRY_HARVEST_KC_END = 0.4
LEGAL_NOTE = (
    "Pobór wody do nawadniania powyżej 5 m³ na dobę (z ujęcia własnego lub cieku) wymaga pozwolenia "
    "wodnoprawnego lub zgłoszenia wodnoprawnego (ustawa Prawo wodne, Wody Polskie). Przed budową ujęcia lub "
    "deszczowni sprawdź wymagania w nadzorze wodnym PGW Wody Polskie."
)


def _project(sim: Simulation, crop: Crop, day: date, forecast: pd.DataFrame) -> tuple[list[date], np.ndarray, float]:
    i = sim.days.index(day)
    dr = float(sim.depletion[i])
    days = list(forecast.index)
    cal = calendar(crop, days)
    taw = float(sim.taw[i])
    p_base = crop.p
    out = []
    etc_sum = 0.0
    for k in range(len(days)):
        e0 = float(forecast["et0_mm"].iloc[k])
        kc = cal.kc[k] if cal.in_season[k] else crop.kc_off
        p_adj = float(np.clip(p_base + 0.04 * (5 - kc * e0), 0.1, 0.8))
        raw = p_adj * taw
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p_adj) * taw))
        etc = ks * kc * e0
        etc_sum += etc
        dr = float(np.clip(dr - float(forecast["precip_mm"].iloc[k]) + etc, 0, taw))
        out.append(dr)
    return days, np.array(out), etc_sum


def advise(sim: Simulation | None, crop: Crop, parcel: Parcel, day: date, forecast: pd.DataFrame) -> IrrigationAdvice:
    if sim is None:
        return IrrigationAdvice(status="nie dotyczy", reason="Brak modelu wody w glebie.", legal_note=LEGAL_NOTE)
    if parcel.is_agricultural is False:
        return IrrigationAdvice(
            status="nie dotyczy",
            reason="Działka nie jest użytkiem rolnym wg EGiB – zalecenia nawadniania nie są wydawane.",
            legal_note=LEGAL_NOTE,
        )
    i = sim.days.index(day)
    if not sim.in_season[i]:
        return IrrigationAdvice(
            status="nie dotyczy",
            reason=f"{crop.name}: {day:%d.%m.%Y} jest poza okresem wegetacji – nawadnianie niezasadne.",
            legal_note=LEGAL_NOTE,
        )
    if day.month in WINTER_MONTHS:
        return IrrigationAdvice(
            status="nie dotyczy",
            reason=f"{crop.name}: {day:%d.%m.%Y} to okres spoczynku zimowego – nawadnianie niezasadne.",
            legal_note=LEGAL_NOTE,
        )
    if sim.stage[i] == "dojrzewanie" and crop.kc_end <= DRY_HARVEST_KC_END:
        return IrrigationAdvice(
            status="niezalecane",
            reason=f"{crop.name}: faza dojrzewania – nawadnianie nie zwiększy już plonu, a może opóźnić zbiór.",
            legal_note=LEGAL_NOTE,
        )
    taw, raw, dr = float(sim.taw[i]), float(sim.raw[i]), float(sim.depletion[i])
    has_forecast = forecast is not None and len(forecast) > 0
    fc_precip = float(forecast["precip_mm"].sum()) if has_forecast else None
    if has_forecast:
        days, projected, fc_etc = _project(sim, crop, day, forecast)
        over = [d for d, v in zip(days, projected, strict=True) if v > raw]
    else:
        days, projected, fc_etc, over = [], np.array([]), None, []
    if dr > raw:
        first = day
    elif over:
        first = over[0]
    else:
        first = None
    if first is None:
        status = "niezalecane" if dr < 0.6 * raw else "monitoruj"
        reason = (
            f"Zubożenie wody w strefie korzeni {dr:.0f} mm jest poniżej progu stresu {raw:.0f} mm "
            f"(w glebie zostało {100 * (1 - dr / taw):.0f}% wody dostępnej dla roślin)."
        )
        if has_forecast:
            reason += f" Prognoza na 7 dni: opad {fc_precip:.0f} mm – próg nie zostanie przekroczony."
        else:
            reason += " Brak prognozy dla daty historycznej – ocena na dzień analizy."
        return IrrigationAdvice(
            status=status,
            reason=reason,
            forecast_precip_7d_mm=round(fc_precip, 1) if fc_precip is not None else None,
            forecast_etc_7d_mm=round(fc_etc, 1) if fc_etc is not None else None,
            forecast_available=has_forecast,
            legal_note=LEGAL_NOTE,
        )
    dr_at = dr if first == day else float(projected[days.index(first)])
    net = round(dr_at, 0)
    split = max(1, int(np.ceil(net / MAX_SINGLE_DOSE_MM)))
    gross = round(net / APPLICATION_EFFICIENCY, 0)
    when = "od razu" if first == day else f"około {first:%d.%m.%Y}"
    reason = (
        f"Zubożenie {dr:.0f} mm {'przekracza' if dr > raw else 'przekroczy'} próg stresu {raw:.0f} mm "
        f"(pojemność strefy korzeni {taw:.0f} mm). Termin: {when}."
    )
    if has_forecast:
        reason += f" Prognoza opadu na 7 dni: {fc_precip:.0f} mm."
    else:
        reason += " Data historyczna – bez prognozy."
    return IrrigationAdvice(
        status="zalecane",
        reason=reason,
        first_day=first,
        net_dose_mm=net,
        gross_dose_mm=gross,
        split_into=split,
        volume_m3=round(gross * parcel.area_ha * 10, 0),
        forecast_precip_7d_mm=round(fc_precip, 1) if fc_precip is not None else None,
        forecast_etc_7d_mm=round(fc_etc, 1) if fc_etc is not None else None,
        forecast_available=has_forecast,
        legal_note=LEGAL_NOTE,
    )
