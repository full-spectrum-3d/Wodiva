from __future__ import annotations

from app.core.schemas import SoilInfo, WaterState
from app.land.models import DataStatus, LandResult, Level, SectionConfidence

# ten sam próg co water.service.MIN_RELIABLE_YEARS (land nie importuje water)
MIN_RELIABLE_YEARS = 3


def _level(score: float) -> Level:
    if score >= 0.7:
        return Level.high
    if score >= 0.45:
        return Level.medium
    return Level.low


def _section(name: str, score: float, reasons: list[str]) -> SectionConfidence:
    score = round(max(0.0, min(1.0, score)), 2)
    return SectionConfidence(section=name, level=_level(score), score=score, reasons=reasons)


def water_section(water: WaterState | None, soil: SoilInfo | None) -> SectionConfidence:
    if water is None:
        return _section("ocena wilgotności", 0.0, ["brak bilansu wodnego"])
    score, reasons = 0.8, [f"bilans wodny z danych meteorologicznych za {len(water.climate.years_analyzed)} lat"]
    if len(water.climate.years_analyzed) < MIN_RELIABLE_YEARS:
        score -= 0.4
        reasons.append("krótka historia meteo: stan wody w glebie może być zaniżony")
    if water.era5_until is None:
        score -= 0.1
        reasons.append("historia meteo z archiwum Open-Meteo zamiast kostki ERA5")
    check = water.station_check
    if check is not None and check.distance_km > 30:
        score -= 0.1
        reasons.append(f"najbliższa stacja IMGW do kontroli ok. {check.distance_km:.0f} km")
    if soil is None or soil.confidence == "niska":
        score -= 0.2
        reasons.append("dane glebowe niepewne")
    if water.soil_water is None:
        score -= 0.2
        reasons.append("poza sezonem uprawy: bez bilansu wody w glebie")
    reasons.append("dane siatkowe opisują okolicę działki, nie pomiar na polu")
    return _section("ocena wilgotności", score, reasons)


def satellite_section(land: LandResult) -> SectionConfidence:
    s = land.satellite
    if s is None or s.latest is None:
        return _section("satelita", 0.0, ["brak bezchmurnego zdjęcia"])
    score, reasons = 0.8, []
    if not s.interpretable:
        score = 0.3
        reasons.append(f"faza „{s.phase_label}” nie pozwala ocenić suszy ze zdjęcia")
    if s.latest.effective_pixels < 10:
        score -= 0.3
        reasons.append(f"mało pikseli w działce ({s.latest.effective_pixels:.0f})")
    if s.latest.clear_fraction < 0.8:
        score -= 0.15
        reasons.append(f"część działki pod chmurą ({1 - s.latest.clear_fraction:.0%})")
    if len(s.history) < 5:
        score -= 0.15
        reasons.append(f"tylko {len(s.history)} lat odniesienia")
    reasons.append("w poprzednich latach na działce mogła rosnąć inna uprawa")
    return _section("satelita", score, reasons)


def radar_section(land: LandResult) -> SectionConfidence:
    r = land.radar
    if r is None or r.latest is None:
        return _section("radar", 0.0, ["brak zdjęcia radarowego"])
    score = 0.55 if r.reference_years >= 5 else 0.4
    reasons = ["radar mierzy wierzchnią warstwę gleby i roślinność", f"{r.reference_years} lat odniesienia"]
    if r.recent_rain:
        score -= 0.15
        reasons.append("świeży opad zaburza sygnał")
    return _section("radar", score, reasons)


def terrain_section(land: LandResult) -> SectionConfidence:
    t = land.terrain
    if t is None or t.status == DataStatus.missing:
        return _section("teren", 0.0, ["brak modelu terenu"])
    if t.status == DataStatus.ok:
        return _section("teren", 0.85, [f"NMT GUGiK, siatka {t.resolution_m} m"])
    return _section("teren", 0.35, ["zapasowy model 30 m z roślinnością i zabudową"])


def hydro_section(land: LandResult) -> SectionConfidence:
    h = land.hydro
    if h is None or h.status == DataStatus.missing:
        return _section("hydrologia", 0.0, ["brak danych BDOT10k"])
    score = 0.75 if h.status == DataStatus.ok else 0.5
    return _section(
        "hydrologia",
        score,
        ["BDOT10k odczytany z mapy, dokładność kilka metrów", "aktualność zależy od aktualizacji BDOT10k"],
    )


def assess(water: WaterState | None, soil: SoilInfo | None, land: LandResult) -> list[SectionConfidence]:
    sections = [
        water_section(water, soil),
        satellite_section(land),
        radar_section(land),
        terrain_section(land),
        hydro_section(land),
    ]
    core = [s.score for s in sections if s.section in ("ocena wilgotności", "teren", "hydrologia")]
    overall = sum(core) / len(core) if core else 0.0
    sections.append(
        _section(
            "rekomendacje",
            overall,
            ["wynikają z oceny wilgotności, terenu i hydrologii", "wymagają sprawdzenia w terenie"],
        )
    )
    return sections
