from dataclasses import dataclass
from datetime import date

import numpy as np

from app.core.schemas import ScenarioResult, SoilLayer
from app.water.engine.crops import Crop, season_for_year
from app.water.engine.soil_hydraulics import saxton_rawls
from app.water.engine.soil_water import Modifiers, Simulation, simulate, stress_days_by_season

OM_PER_SOC = 1.724


@dataclass(frozen=True)
class Scenario:
    code: str
    name: str
    description: str


SCENARIOS = [
    Scenario(
        "mulcz",
        "Mulcz i resztki pożniwne",
        "Pozostawienie resztek / mulczu (ok. 50% pokrycia) zmniejsza parowanie z gleby o ok. 25% (FAO-56, rozdz. 11).",
    ),
    Scenario(
        "prochnica",
        "+1 punkt procentowy materii organicznej",
        "Wzrost zawartości materii organicznej w warstwie 0–30 cm o 1 p.p. zwiększa pojemność wodną "
        "(pedotransfer Saxton i Rawls 2006).",
    ),
    Scenario(
        "splyw",
        "Zatrzymanie spływu powierzchniowego",
        "Pasy buforowe, uprawa w poprzek stoku i zastoiska ograniczają odpływ powierzchniowy o ok. 70%.",
    ),
]


def layers_with_more_om(layers: list[SoilLayer], delta_om: float = 1.0) -> list[SoilLayer]:
    out = []
    for layer in layers:
        if layer.top_cm >= 30:
            out.append(layer)
            continue
        om = layer.soc_pct * OM_PER_SOC + delta_om
        fc, wp = saxton_rawls(layer.sand_pct, layer.clay_pct, om)
        out.append(layer.model_copy(update={"theta_fc": fc, "theta_wp": wp, "awc": fc - wp}))
    return out


def modifiers(code: str, layers: list[SoilLayer]) -> Modifiers:
    if code == "mulcz":
        return Modifiers(kc_evap_factor=0.75)
    if code == "prochnica":
        return Modifiers(layers=layers_with_more_om(layers))
    if code == "splyw":
        return Modifiers(runoff_factor=0.3)
    return Modifiers()


def complete_season_years(crop: Crop, sim: Simulation, until: date, history_years: int = 10) -> list[int]:
    first = sim.days[0]
    years = []
    for y in sorted({int(v) for v in np.unique(sim.season_year) if v}):
        s = season_for_year(crop, y)
        if s.sow > first and s.harvest <= until and y >= until.year - history_years:
            years.append(y)
    return years


def run_scenarios(
    baseline: Simulation,
    precip: np.ndarray,
    et0: np.ndarray,
    crop: Crop,
    layers: list[SoilLayer],
    runoff_coef: float,
    day: date,
    phase_shift: tuple[int, int] | None = None,
) -> list[ScenarioResult]:
    base_stress = stress_days_by_season(baseline, until=day)
    complete = complete_season_years(crop, baseline, day)
    if not complete:
        return []
    reference = max(complete, key=lambda y: (base_stress.get(y, 0), y))
    ref_harvest = season_for_year(crop, reference).harvest
    index = {d: i for i, d in enumerate(baseline.days)}
    crit = _critical_index(crop, reference, index)
    results = []
    for sc in SCENARIOS:
        sim = simulate(baseline.days, precip, et0, crop, layers, runoff_coef, phase_shift, modifiers(sc.code, layers))
        stress = stress_days_by_season(sim, until=ref_harvest)
        results.append(
            ScenarioResult(
                code=sc.code,
                name=sc.name,
                description=sc.description,
                reference_year=reference,
                stress_days_baseline=base_stress.get(reference, 0),
                stress_days_scenario=stress.get(reference, 0),
                stress_days_saved=base_stress.get(reference, 0) - stress.get(reference, 0),
                available_pct_baseline=round(float(np.nanmean(baseline.available_pct[crit])), 1),
                available_pct_scenario=round(float(np.nanmean(sim.available_pct[crit])), 1),
            )
        )
    return results


def _critical_index(crop: Crop, year: int, index: dict[date, int]) -> list[int]:
    s = season_for_year(crop, year)
    month, day = (int(x) for x in crop.critical_start.split("-"))
    em, ed = (int(x) for x in crop.critical_end.split("-"))
    start = date(s.harvest.year if month <= s.harvest.month else s.sow.year, month, day)
    end = date(s.harvest.year if em <= s.harvest.month else s.sow.year, em, ed)
    idx = [i for d, i in index.items() if start <= d <= end]
    return idx or [i for d, i in index.items() if s.sow <= d <= s.harvest]
