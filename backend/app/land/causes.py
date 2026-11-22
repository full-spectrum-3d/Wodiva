from app.core.schemas import SoilInfo, WaterState
from app.land.models import Cause, DataStatus, LandResult, Level

REFERENCE_AWC_MM = 150.0
LIGHT_SOIL_CATEGORIES = {"I", "II"}


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def precipitation(water: WaterState) -> Cause:
    c = water.climate
    if c.precip_30d_norm_mm is None or c.precip_30d_norm_mm <= 0:
        return Cause(
            key="opad",
            label="Niedobór opadów",
            active=bool(c.kbw_drought),
            score=0.5 if c.kbw_drought else 0,
            explanation=f"Klimatyczny bilans wodny z 60 dni: {c.kbw_60d_mm:+.0f} mm; brak normy opadu do porównania.",
            evidence=["E02", "E12"],
        )
    deficit = c.precip_30d_norm_mm - c.precip_30d_mm
    share = deficit / c.precip_30d_norm_mm
    spi_dry = c.spi_3 is not None and c.spi_3 <= -1.0
    active = share >= 0.2 or spi_dry or bool(c.kbw_drought)
    text = (
        f"W ostatnich 30 dniach spadło {c.precip_30d_mm:.0f} mm, przy średniej {c.precip_30d_norm_mm:.0f} mm "
        "dla tego okresu z 10 lat"
    )
    if c.spi_3 is not None:
        text += f"; wskaźnik opadu SPI-3 = {c.spi_3:.1f}"
    text += f"; klimatyczny bilans wodny z 60 dni {c.kbw_60d_mm:+.0f} mm"
    if c.kbw_threshold_mm is not None and c.kbw_period_mm is not None:
        text += f" (okres {c.kbw_period_label}: {c.kbw_period_mm:+.0f} mm, próg suszy {c.kbw_threshold_mm:+.0f} mm)"
    if c.dry_spell_current_days:
        text += f"; bez opadu od {c.dry_spell_current_days} dni"
    return Cause(
        key="opad",
        label="Niedobór opadów",
        active=active,
        score=_clamp(max(share, -(c.spi_3 or 0) / 2)),
        contribution_mm=round(max(deficit, 0.0), 1),
        explanation=text + ".",
        evidence=["E02", "E12"],
    )


def evaporation(water: WaterState) -> Cause:
    c = water.climate
    anomaly = c.et0_anomaly_pct or 0.0
    excess = c.et0_30d_mm * anomaly / (100 + anomaly) if anomaly > -100 else 0.0
    active = anomaly >= 10 or c.hot_days_30d >= 5
    text = f"Zapotrzebowanie powietrza na wodę (ET0) w ostatnich 30 dniach: {c.et0_30d_mm:.0f} mm"
    if c.et0_anomaly_pct is not None:
        text += f", {c.et0_anomaly_pct:+.0f}% względem średniej z 10 lat"
    if c.hot_days_30d:
        text += f"; dni upalnych w ostatnich 30 dniach: {c.hot_days_30d}"
    return Cause(
        key="parowanie",
        label="Wysokie parowanie (upał)",
        active=active,
        score=_clamp(anomaly / 30 + c.hot_days_30d / 15),
        contribution_mm=round(max(excess, 0.0), 1),
        explanation=text + ".",
        evidence=["E01", "E12"],
    )


def soil(soil_info: SoilInfo | None) -> Cause:
    if soil_info is None:
        return Cause(
            key="gleba",
            label="Mała pojemność wodna gleby",
            active=False,
            score=0,
            explanation="Brak danych glebowych.",
            evidence=["E02"],
        )
    sand = soil_info.layers[0].sand_pct if soil_info.layers else None
    light = (soil_info.iung_category or "") in LIGHT_SOIL_CATEGORIES or (sand or 0) >= 65
    shortfall = REFERENCE_AWC_MM - soil_info.awc_mm_100cm
    active = light or soil_info.awc_mm_100cm < 120
    text = (
        f"Gleba magazynuje ok. {soil_info.awc_mm_100cm:.0f} mm wody dostępnej dla roślin w warstwie 0–100 cm "
        f"({soil_info.texture_topsoil}"
    )
    text += f", piasek {sand:.0f}%)" if sand is not None else ")"
    if soil_info.iung_category:
        text += f"; kategoria podatności na suszę IUNG: {soil_info.iung_category}"
    text += f"; materia organiczna {soil_info.organic_matter_pct_topsoil:.1f}%"
    return Cause(
        key="gleba",
        label="Mała pojemność wodna gleby",
        active=active,
        score=_clamp(shortfall / 100 + (0.3 if light else 0)),
        contribution_mm=round(max(shortfall, 0.0), 1),
        explanation=text + ".",
        evidence=["E02", "E07", "E12"],
    )


def runoff(water: WaterState, land: LandResult) -> Cause:
    t = land.terrain
    runoff_mm = water.soil_water.runoff_season_mm if water.soil_water else None
    risk = t.runoff_risk if t is not None else None
    if risk is None and runoff_mm is None:
        return Cause(
            key="splyw",
            label="Odpływ powierzchniowy",
            active=False,
            score=0,
            explanation="Brak danych o ukształtowaniu terenu.",
            evidence=["E12"],
        )
    active = (runoff_mm or 0) >= 5 or risk in (Level.medium, Level.high)
    parts = []
    if t is not None and t.mean_slope_pct is not None and risk is not None:
        parts.append(f"średni spadek terenu {t.mean_slope_pct:.1f}%, ryzyko spływu {risk.value}")
        if t.flow_path_length_m:
            parts.append(f"skupiony spływ na odcinku ok. {t.flow_path_length_m:.0f} m w obrębie działki")
    if runoff_mm is not None:
        parts.append(f"w tym sezonie z działki odpłynęło ok. {runoff_mm:.0f} mm opadu (model wody)")
    score = (
        {Level.low: 0.1, Level.medium: 0.5, Level.high: 0.85}.get(risk, 0.2) if risk else _clamp((runoff_mm or 0) / 30)
    )
    return Cause(
        key="splyw",
        label="Odpływ powierzchniowy",
        active=active,
        score=score,
        contribution_mm=runoff_mm,
        explanation="; ".join(parts).capitalize() + ".",
        evidence=["E05", "E12", "E16"],
    )


def landscape(land: LandResult) -> Cause:
    h = land.hydro
    if h is None or h.status == DataStatus.missing:
        return Cause(
            key="krajobraz",
            label="Brak retencji w krajobrazie",
            active=False,
            score=0,
            explanation="Brak danych o otoczeniu działki.",
            evidence=["E04"],
        )
    poor = h.water_area_ha_500m < 0.5 and h.wetland_area_ha_500m < 0.5 and h.tree_cover_pct_500m < 5
    text = (
        f"W promieniu {h.search_radius_m:.0f} m: wody powierzchniowe {h.water_area_ha_500m:.1f} ha, "
        f"mokradła {h.wetland_area_ha_500m:.1f} ha, "
        f"zadrzewienia {h.tree_cover_pct_500m:.0f}% powierzchni"
    )
    if h.ditch_distance_m is not None:
        text += (
            "; rów melioracyjny na działce lub przy jej granicy"
            if h.ditch_distance_m <= 5
            else f"; najbliższy rów melioracyjny ok. {h.ditch_distance_m:.0f} m"
        )
    return Cause(
        key="krajobraz",
        label="Brak retencji w krajobrazie",
        active=poor,
        score=0.7 if poor else 0.2,
        explanation=text + ".",
        evidence=["E04", "E05", "E12"],
    )


def identify(water: WaterState, soil_info: SoilInfo | None, land: LandResult) -> list[Cause]:
    causes = [precipitation(water), evaporation(water), soil(soil_info), runoff(water, land), landscape(land)]
    return sorted(
        causes, key=lambda c: (not c.active, -(c.contribution_mm if c.contribution_mm is not None else c.score * 50))
    )
