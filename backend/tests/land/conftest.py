from datetime import date
from pathlib import Path

import pytest
from shapely import wkt
from shapely.geometry import mapping

from app.core.config import get_settings
from app.core.mock import mock_report
from app.core.schemas import AnalyzeRequest
from app.land import cache as land_cache
from app.land.collect import LandArtifacts
from app.land.geo import PL_CRS, reproject
from app.land.models import (
    DataStatus,
    DroughtContext,
    GeoFeature,
    HydroInfo,
    LandResult,
    LandSourceNote,
    Level,
    RadarState,
    SatelliteObservation,
    SatelliteState,
    TerrainInfo,
)
from app.report import store

DAY = date(2025, 6, 20)
CROP = "kukurydza_ziarno"


@pytest.fixture(autouse=True)
def isolated_land_storage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_path", tmp_path / "cache.sqlite")
    monkeypatch.setattr(land_cache, "_cache", None)
    monkeypatch.setattr(store, "_conn", None)
    yield


@pytest.fixture
def mock():
    return mock_report(AnalyzeRequest(parcel_id="060802_2.0001.MOCK", date=DAY, crop=CROP, soil_category="II"))


@pytest.fixture
def parcel(mock):
    return mock.parcel


@pytest.fixture
def water(mock):
    return mock.water


@pytest.fixture
def soil(mock):
    return mock.soil


@pytest.fixture
def irrigation(mock):
    return mock.irrigation


@pytest.fixture
def land(parcel) -> LandResult:
    geom = wkt.loads(parcel.geometry_wkt_2180)
    center = reproject(geom.centroid.buffer(10), PL_CRS, 4326)
    line = reproject(geom.centroid.buffer(3), PL_CRS, 4326)
    depression = GeoFeature(
        kind="zagłębienie",
        geometry=mapping(center),
        properties={"area_m2": 320, "max_depth_m": 0.4, "volume_m3": 60, "inside_parcel_share": 1.0},
    )
    channel = GeoFeature(
        kind="linia spływu", geometry=mapping(line), properties={"length_m": 140, "max_contributing_area_ha": 4.2}
    )
    return LandResult(
        satellite=SatelliteState(
            latest=SatelliteObservation(
                date=date(2025, 6, 17),
                scene_id="S2",
                ndvi=0.42,
                ndmi=0.02,
                ndwi=-0.4,
                ndre=0.3,
                clear_fraction=0.95,
                effective_pixels=280,
            ),
            history=[],
            phase="vegetative",
            phase_label="rozwój wegetatywny",
            interpretable=True,
            vci_ndvi=0.18,
            vci_ndmi=0.22,
            anomaly_class="silnie poniżej normy",
            interpretation="Stan roślin silnie poniżej normy.",
            phase_offset_days=6,
            surface_state="roślinność",
        ),
        radar=RadarState(interpretation="Brak zdjęcia radarowego.", status=DataStatus.missing),
        terrain=TerrainInfo(
            dem_source="NMT GUGiK (usługa wysokości)",
            resolution_m=1.0,
            mean_slope_pct=3.4,
            max_slope_pct=6.1,
            twi_mean=6.2,
            runoff_risk=Level.medium,
            depression_area_m2=320,
            depression_volume_m3=60,
            flow_path_length_m=140,
            outflow_share=0.8,
            features=[depression, channel],
        ),
        hydro=HydroInfo(
            ditch_distance_m=60,
            water_area_ha_500m=0.1,
            wetland_area_ha_500m=0.0,
            tree_cover_pct_500m=2.0,
        ),
        drought=DroughtContext(
            date=date(2025, 6, 11), cdi_class="ostrzeżenie", cdi_meaning="deficyt opadu i niedobór wilgotności gleby"
        ),
        sources=[LandSourceNote(key="sentinel2"), LandSourceNote(key="nmt"), LandSourceNote(key="bdot10k")],
    )


@pytest.fixture
def artifacts() -> LandArtifacts:
    return LandArtifacts()
