from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date

from shapely.geometry import mapping

from app.land.engine import phenology, terrain
from app.land.engine.satellite_indices import vci
from app.land.geo import PL_CRS, parcel_geometry, reproject
from app.land.models import (
    DataStatus,
    DroughtContext,
    GeoFeature,
    HydroInfo,
    LandNote,
    LandResult,
    LandSourceNote,
    Level,
    RadarObservation,
    RadarState,
    SatelliteState,
    TerrainInfo,
)
from app.land.settings import land_settings
from app.land.sources import bdot, dem, edo, pigpib, sentinel1, sentinel2

SMALL_PARCEL_HA = 0.3
TERRAIN_BUFFER_M = 150.0
log = logging.getLogger("wodiva.land")


@dataclass
class LandArtifacts:
    terrain: terrain.TerrainAnalysis | None = None
    dem: dem.Dem | None = None
    hydro: bdot.HydroLayers | None = None
    radar_history: list[RadarObservation] = field(default_factory=list)


async def _timed(name: str, coro, timings: dict[str, float], timeout: float):
    start = time.perf_counter()
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception as error:
        log.warning("źródło %s: %s: %s", name, type(error).__name__, error)
        return error
    finally:
        timings[name] = round(time.perf_counter() - start, 2)


def _history_label(history, years: int) -> str:
    landsat = sum(1 for h in history if h.sensor != "Sentinel-2")
    text = f"{len(history)} z {years} lat"
    if landsat:
        text += f", w tym {landsat} z Landsat 30 m"
    return text


def surface_state(phase: str, ndvi: float | None) -> str:
    if ndvi is None:
        return "nieznany"
    if phase == "after_harvest" and ndvi < 0.35:
        return "po zbiorze"
    if ndvi < 0.25:
        return "goła gleba"
    return "roślinność"


async def _satellite(geom, small: bool, crop: str, day: date, deadline: float) -> SatelliteState:
    settings = land_settings()
    geom_wgs84 = reproject(geom, PL_CRS, 4326)
    bbox = geom_wgs84.bounds
    inner = 0.0 if small else 5.0
    phase = phenology.phase_on(crop, day)
    label = phenology.PHASE_LABELS[phase]
    season_task = asyncio.create_task(sentinel2.season_points(geom, geom_wgs84, bbox, day, inner))
    try:
        latest, sharpened = await asyncio.wait_for(
            sentinel2.latest(geom, geom_wgs84, bbox, day, inner), max(deadline - time.monotonic() - 2, 1)
        )
    except TimeoutError:
        latest, sharpened = None, False
    history = []
    if latest is not None and phenology.is_interpretable(phase):
        history = await sentinel2.same_window_history(
            geom,
            geom_wgs84,
            bbox,
            day,
            settings.sat_history_years,
            inner,
            max(deadline - time.monotonic() - 1, 0.5),
            settings.sat_history_background,
        )
    try:
        points = await asyncio.wait_for(season_task, max(deadline - time.monotonic() - 0.5, 0.1))
    except Exception:
        points = []
    offset = phenology.phase_offset(crop, [(d.timetuple().tm_yday, v) for d, v in points]) if points else None
    if latest is None:
        return SatelliteState(
            history=history,
            phase=phase,
            phase_label=label,
            interpretable=False,
            sharpened=sharpened,
            phase_offset_days=offset,
            season_points=len(points),
            interpretation=(
                "Brak bezchmurnego zdjęcia Sentinel-2 z ostatnich 40 dni przed datą analizy albo nie udało się go "
                "pobrać w limicie czasu."
            ),
            status=DataStatus.missing,
        )
    interpretable = phenology.is_interpretable(phase)
    vci_ndvi = vci(latest.ndvi, [h.ndvi for h in history if h.ndvi is not None])
    vci_ndmi = vci(latest.ndmi, [h.ndmi for h in history if h.ndmi is not None])
    klass = phenology.anomaly_class([v for v in (vci_ndvi, vci_ndmi) if v is not None]) if interpretable else None
    age = (day - latest.date).days
    if not interpretable:
        text = (
            f"Uprawa jest w fazie „{label}”. Niski lub zmienny wskaźnik zieleni w tej fazie jest naturalny "
            "i nie świadczy o suszy, dlatego zdjęcia satelitarnego nie używamy tu do oceny niedoboru wody."
        )
    elif klass is None:
        text = (
            f"Zdjęcie z {latest.date.isoformat()} ({age} dni przed datą analizy): NDVI {latest.ndvi}, "
            f"NDMI {latest.ndmi}, NDRE {latest.ndre}. "
            "Za mało zdjęć z tej samej pory roku w poprzednich latach "
            f"({_history_label(history, settings.sat_history_years)}), by porównać stan roślin z normą."
        )
    else:
        text = (
            f"Zdjęcie z {latest.date.isoformat()} ({age} dni przed datą analizy): stan roślin {klass} "
            "na tle poprzednich lat w tej samej porze roku "
            f"({_history_label(history, settings.sat_history_years)}; VCI NDVI {vci_ndvi}, VCI NDMI "
            f"{vci_ndmi}). "
            "W poprzednich latach na działce mogła rosnąć inna uprawa."
        )
    if interpretable and latest.ndvi is not None and latest.ndvi < 0.25:
        text += (
            "Bardzo niski NDVI w fazie, w której uprawa powinna być zielona: sprawdź na polu, czy nie ma gołej "
            "gleby, zbioru lub uszkodzeń."
        )
    if offset:
        text += f" Rozwój uprawy w tym sezonie jest przesunięty o ok. {offset:+d} dni względem kalendarza."
    return SatelliteState(
        latest=latest,
        history=sorted(history, key=lambda h: h.date),
        phase=phase,
        phase_label=label,
        interpretable=interpretable,
        vci_ndvi=vci_ndvi,
        vci_ndmi=vci_ndmi,
        anomaly_class=klass,
        interpretation=text,
        sharpened=sharpened,
        phase_offset_days=offset,
        season_points=len(points),
        surface_state=surface_state(phase, latest.ndvi),
        status=DataStatus.ok if latest.clear_fraction >= 0.6 else DataStatus.partial,
    )


async def _radar(geom, day: date, deadline: float):
    geom_wgs84 = reproject(geom, PL_CRS, 4326)
    return await sentinel1.latest_and_history(
        geom,
        geom_wgs84,
        geom_wgs84.bounds,
        day,
        land_settings().sat_history_years,
        max(deadline - time.monotonic() - 1, 1),
    )


def radar_state(
    latest: RadarObservation | None, history: list[RadarObservation], phase: str, recent_rain_mm: float | None
) -> RadarState:
    if latest is None:
        return RadarState(
            interpretation="Brak zdjęcia radarowego Sentinel-1 z 12 dni przed datą analizy.", status=DataStatus.missing
        )
    recent_rain = recent_rain_mm is not None and recent_rain_mm >= 5
    if len(history) < 3:
        return RadarState(
            latest=latest,
            reference_years=len(history),
            recent_rain=recent_rain,
            interpretation=f"Zdjęcie radarowe z {latest.date.isoformat()}; za mało lat do porównania ({len(history)}).",
            status=DataStatus.partial,
        )
    vv_ref = sorted(h.vv_db for h in history)[len(history) // 2]
    ratio_ref = sorted(h.vh_vv_db for h in history)[len(history) // 2]
    vv_anomaly = round(latest.vv_db - vv_ref, 2)
    ratio_anomaly = round(latest.vh_vv_db - ratio_ref, 2)
    parts = [f"Zdjęcie radarowe z {latest.date.isoformat()} na tle {len(history)} poprzednich lat."]
    if phenology.is_interpretable(phase):
        if ratio_anomaly <= -1.5:
            parts.append(
                f"Stosunek VH/VV niższy o {abs(ratio_anomaly)} dB niż zwykle: mniej biomasy niż w tej "
                "porze w poprzednich latach."
            )
        elif ratio_anomaly >= 1.5:
            parts.append(f"Stosunek VH/VV wyższy o {ratio_anomaly} dB niż zwykle: więcej biomasy niż zwykle.")
        else:
            parts.append("Stosunek VH/VV w normie: ilość biomasy podobna jak w poprzednich latach.")
    elif vv_anomaly <= -1.5:
        parts.append(
            f"Sygnał VV niższy o {abs(vv_anomaly)} dB niż zwykle: wierzchnia warstwa gleby (kilka cm) "
            "prawdopodobnie suchsza niż zwykle."
        )
    elif vv_anomaly >= 1.5:
        parts.append(
            f"Sygnał VV wyższy o {vv_anomaly} dB niż zwykle: wierzchnia warstwa gleby prawdopodobnie "
            "wilgotniejsza niż zwykle."
        )
    else:
        parts.append("Sygnał VV w normie dla tej pory roku.")
    if recent_rain:
        parts.append("W ostatnich 3 dniach padało, co chwilowo podnosi sygnał radaru; ostrożnie z wnioskami.")
    parts.append("Radar mierzy tylko wierzchnią warstwę gleby i roślinność; na sygnał wpływa też uprawa roli.")
    return RadarState(
        latest=latest,
        reference_years=len(history),
        vv_anomaly_db=vv_anomaly,
        vh_vv_anomaly_db=ratio_anomaly,
        recent_rain=recent_rain,
        interpretation=" ".join(parts),
    )


async def _terrain(geom):
    model = await dem.load(geom, TERRAIN_BUFFER_M)
    if model is None:
        return None, None
    if model.source == "nmt":
        params = dict(
            depth_threshold_m=0.15, min_depression_m2=max(50.0, 4 * model.resolution_m**2), channel_area_m2=5000.0
        )
    else:
        params = dict(depth_threshold_m=1.0, min_depression_m2=4 * model.resolution_m**2, channel_area_m2=20000.0)
    analysis = await asyncio.to_thread(terrain.analyze, model.data, model.transform, geom, **params)
    return model, analysis


def terrain_info(model: dem.Dem, analysis: terrain.TerrainAnalysis) -> TerrainInfo:
    features = []
    tolerance = model.resolution_m / 2
    for d in analysis.depressions:
        geom = reproject(d["geometry"].simplify(tolerance), PL_CRS, 4326)
        features.append(
            GeoFeature(
                kind="zagłębienie", geometry=mapping(geom), properties={k: v for k, v in d.items() if k != "geometry"}
            )
        )
    for c in analysis.channels:
        geom = reproject(c["geometry"].simplify(tolerance), PL_CRS, 4326)
        features.append(
            GeoFeature(
                kind="linia spływu", geometry=mapping(geom), properties={k: v for k, v in c.items() if k != "geometry"}
            )
        )
    return TerrainInfo(
        dem_source="NMT GUGiK (usługa wysokości)" if model.source == "nmt" else "Copernicus DEM GLO-30 (zapasowy)",
        resolution_m=model.resolution_m,
        mean_slope_pct=analysis.mean_slope_pct,
        max_slope_pct=analysis.p95_slope_pct,
        twi_mean=analysis.twi_mean,
        runoff_risk=Level(terrain.runoff_risk(analysis.mean_slope_pct, analysis.flow_path_length_m)),
        depression_area_m2=analysis.depression_area_m2,
        depression_volume_m3=analysis.depression_volume_m3,
        flow_path_length_m=analysis.flow_path_length_m,
        outflow_share=analysis.outflow_share,
        features=features,
        status=DataStatus.ok if model.source == "nmt" else DataStatus.partial,
    )


async def _hydro(geom):
    layers = await bdot.load(geom)
    info = bdot.summarize(layers, geom)
    try:
        info.features = await bdot.features(layers, geom, info)
    except Exception as error:
        log.warning("bdot10k atrybuty: %s", type(error).__name__)
    return layers, info


async def collect(
    geometry_wkt_2180: str, area_ha: float, small: bool, centroid_lon: float, centroid_lat: float, crop: str, day: date
) -> tuple[LandResult, LandArtifacts]:
    budget = land_settings().land_budget_s
    deadline = time.monotonic() + budget
    geom = parcel_geometry(geometry_wkt_2180)
    small = small or area_ha < SMALL_PARCEL_HA
    timings: dict[str, float] = {}
    sat, rad, ter, hyd, cdi, gw = await asyncio.gather(
        _timed("sentinel2", _satellite(geom, small, crop, day, deadline), timings, budget),
        _timed("sentinel1", _radar(geom, day, deadline), timings, budget),
        _timed("teren", _terrain(geom), timings, budget),
        _timed("bdot10k", _hydro(geom), timings, budget),
        _timed("edo", edo.cdi(centroid_lon, centroid_lat, day), timings, budget),
        _timed("pig-pib", pigpib.groundwater(geom, day), timings, budget),
    )
    result = LandResult(timings_s=timings)
    artifacts = LandArtifacts()
    notes, sources = result.notes, result.sources
    phase = phenology.phase_on(crop, day)
    years = land_settings().sat_history_years

    if isinstance(sat, SatelliteState):
        result.satellite = sat
        dates = [h.date for h in sat.history] + ([sat.latest.date] if sat.latest else [])
        s2_dates = [h.date for h in sat.history if h.sensor == "Sentinel-2"] + ([sat.latest.date] if sat.latest else [])
        sources.append(
            LandSourceNote(
                key="sentinel2",
                status=sat.status,
                period_start=min(s2_dates, default=None),
                period_end=max(s2_dates, default=None),
                note="wskaźniki NDVI, NDMI, NDWI, NDRE; pasma 20 m (B05, B8A, B11) wyostrzone do 10 m",
            )
        )
        landsat_years = [h for h in sat.history if h.sensor != "Sentinel-2"]
        if landsat_years:
            sources.append(
                LandSourceNote(
                    key="landsat",
                    period_start=min(h.date for h in landsat_years),
                    period_end=max(h.date for h in landsat_years),
                    note=(
                        f"{len(landsat_years)} lat odniesienia sprzed Sentinel-2 lub bez bezchmurnego zdjęcia "
                        "Sentinel-2"
                    ),
                )
            )
            notes.append(
                LandNote(
                    code="landsat_mix",
                    section="satelita",
                    text=(
                        "Część lat odniesienia pochodzi z Landsat (30 m); wskaźniki z dwóch satelitów różnią się "
                        "nieco, więc porównanie z normą jest przybliżone."
                    ),
                )
            )
        if sat.interpretable and sat.latest is not None and len(sat.history) < years:
            notes.append(
                LandNote(
                    code="satellite_history_short",
                    section="satelita",
                    text=(
                        f"Porównanie z normą objęło {len(sat.history)} z {years} poprzednich lat (brak "
                        "bezchmurnych zdjęć z tej pory roku lub limit czasu); brakujące lata pobierają się w "
                        "tle i będą użyte przy kolejnej analizie tej działki."
                    ),
                )
            )
        if sat.phase_offset_days is None:
            notes.append(
                LandNote(
                    code="phase_offset_unknown",
                    section="satelita",
                    text=(
                        "Nie wyznaczono przesunięcia faz uprawy (za mało bezchmurnych zdjęć z bieżącego sezonu); "
                        "model wody liczy z kalendarza upraw."
                    ),
                )
            )
        if small:
            notes.append(
                LandNote(
                    code="small_parcel",
                    section="satelita",
                    text=(
                        "Działka jest mała w porównaniu z pikselem Sentinel-2 (10 m); wynik satelitarny ma niską "
                        "pewność."
                    ),
                    severity="ostrzeżenie",
                )
            )
        if not dates:
            notes.append(
                LandNote(code="satellite_missing", section="satelita", text=sat.interpretation, severity="ostrzeżenie")
            )
    else:
        result.satellite = SatelliteState(
            phase=phase,
            phase_label=phenology.PHASE_LABELS[phase],
            interpretable=False,
            interpretation="Nie udało się pobrać danych Sentinel-2.",
            status=DataStatus.missing,
        )
        sources.append(LandSourceNote(key="sentinel2", status=DataStatus.missing, note=f"błąd: {type(sat).__name__}"))
        notes.append(
            LandNote(
                code="satellite_missing",
                section="satelita",
                text="Brak danych Sentinel-2 w limicie czasu.",
                severity="ostrzeżenie",
            )
        )

    if isinstance(rad, tuple):
        latest, history = rad
        artifacts.radar_history = history
        result.radar = radar_state(latest, history, phase, None)
        sources.append(
            LandSourceNote(
                key="sentinel1",
                status=result.radar.status,
                period_start=min([h.date for h in history], default=latest.date if latest else None),
                period_end=latest.date if latest else None,
            )
        )
    else:
        result.radar = RadarState(interpretation="Nie udało się pobrać danych Sentinel-1.", status=DataStatus.missing)
        sources.append(LandSourceNote(key="sentinel1", status=DataStatus.missing, note=f"błąd: {type(rad).__name__}"))

    if isinstance(ter, tuple) and ter[0] is not None:
        model, analysis = ter
        artifacts.dem, artifacts.terrain = model, analysis
        result.terrain = terrain_info(model, analysis)
        if model.source == "nmt":
            sources.append(LandSourceNote(key="nmt", note=f"wysokości NMT próbkowane w siatce {model.resolution_m} m"))
        else:
            sources.append(
                LandSourceNote(
                    key="nmt", status=DataStatus.missing, note="usługa wysokości NMT nie odpowiedziała w limicie czasu"
                )
            )
            sources.append(LandSourceNote(key="copdem", note=f"model zapasowy, siatka {model.resolution_m} m"))
            notes.append(
                LandNote(
                    code="dem_fallback",
                    section="teren",
                    severity="ostrzeżenie",
                    text=(
                        "Użyto zapasowego modelu terenu Copernicus DEM (30 m, model powierzchni z roślinnością i "
                        "zabudową). Drobne zagłębienia i bruzdy są niewidoczne; miejsca retencji traktuj jako "
                        "orientacyjne."
                    ),
                )
            )
    else:
        result.terrain = TerrainInfo(dem_source="brak", resolution_m=0, status=DataStatus.missing)
        sources.append(LandSourceNote(key="nmt", status=DataStatus.missing))
        notes.append(
            LandNote(
                code="terrain_missing",
                section="teren",
                severity="ostrzeżenie",
                text="Brak modelu terenu: spadek i miejsca retencji nie zostały wyznaczone.",
            )
        )

    if isinstance(hyd, tuple):
        layers, info = hyd
        artifacts.hydro = layers
        result.hydro = info
        sources.append(
            LandSourceNote(
                key="bdot10k",
                status=info.status,
                note=f"promień {int(info.search_radius_m)} m, siatka {layers.resolution_m} m",
            )
        )
        notes.append(
            LandNote(
                code="bdot_raster",
                section="hydrologia",
                text=(
                    "Obiekty wodne odczytane z mapy BDOT10k (rastrowo); odległości są przybliżone do kilku "
                    "metrów, a aktualność zależy od ostatniej aktualizacji BDOT10k w powiecie."
                ),
            )
        )
        if info.tree_cover_pct_parcel + info.water_pct_parcel >= 50:
            notes.append(
                LandNote(
                    code="parcel_not_field",
                    section="działka",
                    severity="ostrzeżenie",
                    text=(
                        f"Według BDOT10k ok. {info.tree_cover_pct_parcel:.0f}% działki to zadrzewienia, a "
                        f"{info.water_pct_parcel:.0f}% wody. Sprawdź, czy wskazana działka jest polem "
                        "uprawnym."
                    ),
                )
            )
    else:
        result.hydro = HydroInfo(status=DataStatus.missing)
        sources.append(LandSourceNote(key="bdot10k", status=DataStatus.missing, note=f"błąd: {type(hyd).__name__}"))
    notes.append(
        LandNote(
            code="mphp_restricted",
            section="hydrologia",
            text=(
                "Usługi MPHP w Hydroportalu ISOK (Wody Polskie) wymagają autoryzacji, więc cieki, rowy i zbiorniki "
                "pochodzą z BDOT10k; dla cieków podajemy identyfikator MPHP zapisany w BDOT10k."
            ),
        )
    )
    if isinstance(gw, dict) and (gw.get("wells") or gw.get("body") or gw.get("major_aquifer")):
        if result.hydro is not None:
            result.hydro.groundwater = gw
        sources.append(LandSourceNote(key="pigpib", note="monitoring wód podziemnych, JCWPd, GZWP"))
        notes.append(
            LandNote(
                code="groundwater_regional",
                section="hydrologia",
                text=(
                    "Wody podziemne opisane są przez najbliższe punkty monitoringu PIG-PIB (do 15 km) i ocenę "
                    "jednolitej części wód podziemnych; nie jest to pomiar na działce."
                ),
            )
        )
        if any("measurement_after_analysis_date" in w for w in gw.get("wells", [])):
            notes.append(
                LandNote(
                    code="groundwater_measurement_later",
                    section="hydrologia",
                    text=(
                        "Usługa PIG-PIB udostępnia tylko ostatni pomiar zwierciadła wody; pomiary późniejsze niż data "
                        "analizy zostały pominięte."
                    ),
                )
            )
    else:
        sources.append(LandSourceNote(key="pigpib", status=DataStatus.missing, note=f"błąd: {type(gw).__name__}"))
        notes.append(
            LandNote(
                code="groundwater_missing",
                section="hydrologia",
                severity="ostrzeżenie",
                text="Usługa PIG-PIB nie odpowiedziała: brak danych o wodach podziemnych w tym raporcie.",
            )
        )

    if isinstance(cdi, DroughtContext):
        result.drought = cdi
        sources.append(LandSourceNote(key="edo", status=cdi.status, period_start=cdi.date, period_end=cdi.date))
        notes.append(
            LandNote(
                code="edo_regional",
                section="tło suszowe",
                text="Wskaźnik CDI z EDO ma rozdzielczość ok. 5 km i opisuje region, nie działkę.",
            )
        )
    else:
        result.drought = DroughtContext(status=DataStatus.missing)
        sources.append(LandSourceNote(key="edo", status=DataStatus.missing, note=f"błąd: {type(cdi).__name__}"))
    return result, artifacts
