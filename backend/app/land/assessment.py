from dataclasses import dataclass, field

from app.core.schemas import WaterState
from app.land.engine import phenology
from app.land.models import DataStatus, LandResult, Level
from app.land.recommend.context import risk_months
from app.land.recommend.rules import months_label

CDI_POINTS = {"alarm": 2.0, "ostrzeżenie": 1.5, "obserwacja": 1.0}
SAT_POINTS = {"silnie poniżej normy": 2.0, "poniżej normy": 1.0}
HEADLINES = {
    Level.high: "Na działce występuje wysokie ryzyko suszy rolniczej.",
    Level.medium: "Na działce występuje podwyższone ryzyko suszy rolniczej.",
    Level.low: "Na działce nie ma obecnie oznak suszy rolniczej.",
}
# Poza okresem wegetacji susza rolnicza nie występuje (IUNG-PIB ocenia ją w sezonie wegetacyjnym).
# Niski zapas wody i deficyt opadów to wtedy ryzyko wejścia w kolejny sezon z niedoborem, nie susza.
OFF_SEASON = {"dormancy", "after_harvest", "before_sowing"}
OFF_SEASON_HEADLINES = {
    Level.medium: (
        "Uprawa jest poza okresem wegetacji ({phase}), więc susza rolnicza teraz nie występuje. "
        "Zapas wody w glebie lub opady są jednak poniżej normy: jest podwyższone ryzyko, "
        "że uprawa wejdzie w kolejny sezon z niedoborem wody."
    ),
    Level.low: (
        "Uprawa jest poza okresem wegetacji ({phase}). Na działce nie ma oznak niedoboru wody przed kolejnym sezonem."
    ),
}


def crop_phase(water: WaterState) -> str | None:
    try:
        return phenology.phase_on(water.crop, water.analysis_date)
    except KeyError:
        return None


@dataclass
class Assessment:
    status: DataStatus
    risk_level: Level | None
    headline: str
    findings: list[str] = field(default_factory=list)


def groundwater_text(groundwater: dict | None) -> str | None:
    if not groundwater:
        return None
    parts = []
    body = groundwater.get("body") or {}
    if body.get("quantitative_status"):
        parts.append(
            f"jednolita część wód podziemnych {body.get('code', '')} ma {body['quantitative_status']} stan ilościowy "
            f"(ocena {body.get('status_year', '')})"
        )
    if body.get("risk"):
        parts.append(f"ryzyko nieosiągnięcia celów: {body['risk']}")
    wells = [w for w in groundwater.get("wells", []) if "water_table_depth_m" in w]
    if wells:
        w = wells[0]
        parts.append(
            f"najbliższy punkt monitoringu ({w.get('place', '')}, {w['distance_km']} km): zwierciadło wody "
            f"{w['water_table_depth_m']} m p.p.t. ({w['measured_on']})"
        )
    aquifer = groundwater.get("major_aquifer") or {}
    if aquifer.get("name"):
        parts.append(f"działka leży nad GZWP {aquifer.get('number', '')} {aquifer['name']}")
    if not parts:
        return None
    return "Wody podziemne (PIG-PIB): " + "; ".join(parts) + "."


def risk_score(water: WaterState, land: LandResult) -> float:
    points = 0.0
    sw = water.soil_water
    if sw is not None:
        points += 3 if sw.available_pct < 30 else 2 if sw.available_pct < 50 else 0
        if sw.percentile_10y is not None:
            points += 3 if sw.percentile_10y <= 10 else 2 if sw.percentile_10y <= 20 else 0
    c = water.climate
    if c.kbw_drought:
        points += 2
    if c.spi_3 is not None:
        points += 2 if c.spi_3 <= -1.5 else 1 if c.spi_3 <= -1.0 else 0
    if c.years_analyzed and len(c.seasons_with_kbw_drought) / len(c.years_analyzed) >= 0.5:
        points += 1
    if land.drought and land.drought.cdi_class:
        points += CDI_POINTS.get(land.drought.cdi_class, 0)
    if land.satellite and land.satellite.interpretable and land.satellite.anomaly_class:
        points += SAT_POINTS.get(land.satellite.anomaly_class, 0)
    return points


LEVEL_ORDER = [Level.low, Level.medium, Level.high]


def level_from(points: float) -> Level:
    if points >= 5:
        return Level.high
    if points >= 2.5:
        return Level.medium
    return Level.low


def assess(water: WaterState | None, land: LandResult) -> Assessment:
    if water is None:
        return Assessment(
            DataStatus.missing,
            None,
            "Nie udało się ocenić sytuacji wodnej działki: brak bilansu wodnego. Bez oceny nie wydajemy rekomendacji.",
        )
    level = level_from(risk_score(water, land))
    headline = HEADLINES[level]
    phase = crop_phase(water)
    if phase in OFF_SEASON:
        level = min(level, Level.medium, key=LEVEL_ORDER.index)
        headline = OFF_SEASON_HEADLINES[level].format(phase=phenology.PHASE_LABELS[phase])
    findings: list[str] = []
    sw = water.soil_water
    if sw is not None:
        text = (
            f"Zapas wody dostępnej dla roślin: ok. {sw.available_pct:.0f}% pojemności w strefie korzeni "
            f"({sw.taw_mm - sw.depletion_mm:.0f} z {sw.taw_mm:.0f} mm)"
        )
        if sw.percentile_10y is not None:
            text += (
                f"; mniej niż w tej dacie w {100 - sw.percentile_10y:.0f}% ostatnich lat"
                if sw.percentile_10y < 50
                else f"; więcej niż w tej dacie w {sw.percentile_10y:.0f}% ostatnich lat"
            )
        findings.append(text + f". Dni stresu wodnego w tym sezonie: {sw.stress_days_season}.")
    else:
        findings.append("Data analizy jest poza sezonem wegetacji uprawy: ocena opiera się na bilansie klimatycznym.")
    c = water.climate
    text = f"Klimatyczny bilans wodny z 60 dni: {c.kbw_60d_mm:+.0f} mm"
    if c.kbw_drought is not None and c.kbw_threshold_mm is not None:
        text += (
            f"; {'poniżej' if c.kbw_drought else 'powyżej'} progu suszy rolniczej dla tej uprawy i gleby "
            f"({c.kbw_threshold_mm:+.0f} mm)"
        )
    findings.append(text + ".")
    months = risk_months(water)
    if months:
        findings.append(
            f"Największe ryzyko niedoboru wody na tej działce występuje w okresie {months_label(months)} "
            f"(na podstawie {len(c.years_analyzed)} lat)."
        )
    if c.years_analyzed:
        findings.append(
            "Susza rolnicza wg klimatycznego bilansu wodnego wystąpiła w "
            f"{len(c.seasons_with_kbw_drought)} z {len(c.years_analyzed)} ostatnich sezonów."
        )
    if land.satellite is not None:
        findings.append(land.satellite.interpretation)
    if land.radar is not None and land.radar.latest is not None:
        findings.append(land.radar.interpretation)
    if land.drought is not None and land.drought.cdi_class:
        findings.append(
            f"Europejskie Obserwatorium Suszy (CDI, {land.drought.date}): {land.drought.cdi_class} – "
            f"{land.drought.cdi_meaning}."
        )
    groundwater = groundwater_text(land.hydro.groundwater if land.hydro else None)
    if groundwater:
        findings.append(groundwater)
    parts = (land.satellite, land.radar, land.terrain, land.hydro, land.drought)
    status = DataStatus.partial if any(p is None or p.status == DataStatus.missing for p in parts) else DataStatus.ok
    return Assessment(status, level, headline, findings)
