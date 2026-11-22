from datetime import date

import numpy as np
import pytest
from rasterio import Affine
from shapely.geometry import box

from app.land.engine import phenology, terrain
from app.land.engine.satellite_indices import coverage_weights, normalized_difference, summarize, vci
from app.land.engine.sharpen import degrade, sharpen_band


def test_sharpen_recovers_linear_band_and_keeps_20m_means():
    rng = np.random.default_rng(1)
    b3, b4, b8 = (rng.uniform(0.02, 0.4, (40, 40)).astype(np.float32) for _ in range(3))
    truth = 0.01 + 0.3 * b3 + 0.5 * b4 + 0.2 * b8
    band20 = degrade(truth)
    sharp, used = sharpen_band(band20, [b3, b4, b8])
    assert used
    assert np.abs(sharp - truth)[2:-2, 2:-2].mean() < 0.01
    assert np.abs(degrade(sharp) - band20)[1:-1, 1:-1].mean() < 0.01


def test_sharpen_falls_back_without_enough_pixels():
    band20 = np.zeros((2, 2), dtype=np.float32)
    bands = [np.zeros((4, 4), dtype=np.float32)] * 3
    _, used = sharpen_band(band20, bands)
    assert not used


def test_coverage_weights_match_area():
    transform = Affine(10, 0, 0, 0, -10, 100)
    geom = box(5, 25, 65, 85)
    weights = coverage_weights(geom, transform, (10, 10), supersample=10)
    assert weights.sum() * 100 == pytest.approx(geom.area, rel=0.02)
    assert weights.max() == pytest.approx(1.0)
    assert 0 < weights[1, 0] < 1


def test_indices_and_summary_ignore_invalid_pixels():
    nir = np.full((4, 4), 0.4, dtype=np.float32)
    red = np.full((4, 4), 0.1, dtype=np.float32)
    ndvi = normalized_difference(nir, red)
    valid = np.ones((4, 4), dtype=bool)
    valid[0, :] = False
    stats = summarize({"ndvi": ndvi}, np.ones((4, 4), dtype=np.float32), valid)
    assert stats["ndvi"] == pytest.approx(0.6)
    assert stats["clear_fraction"] == pytest.approx(0.75)


def test_vci_needs_history_and_range():
    assert vci(0.5, [0.4, 0.6]) is None
    assert vci(0.5, [0.5, 0.51, 0.52]) is None
    assert vci(0.3, [0.3, 0.7, 0.8]) == 0.0
    assert vci(0.8, [0.3, 0.7, 0.8]) == 1.0


@pytest.mark.parametrize(
    "crop,day,phase",
    [
        ("pszenica_ozima", date(2024, 1, 10), "dormancy"),
        ("pszenica_ozima", date(2024, 5, 20), "peak"),
        ("pszenica_ozima", date(2024, 8, 10), "after_harvest"),
        ("kukurydza_ziarno", date(2024, 6, 10), "vegetative"),
        ("kukurydza_ziarno", date(2024, 8, 1), "peak"),
        ("burak_cukrowy", date(2024, 3, 1), "before_sowing"),
    ],
)
def test_phase_on(crop, day, phase):
    assert phenology.phase_on(crop, day) == phase


def test_every_crop_has_calendar():
    from app.water.engine.crops import load_crops

    assert set(load_crops()) <= set(phenology.calendars())


def test_phase_offset_recovers_shift():
    crop = "kukurydza_ziarno"
    points = [(doy, phenology.expected_ndvi(crop, doy - 12)) for doy in (130, 150, 170, 190, 210)]
    assert phenology.phase_offset(crop, points) == 12
    assert phenology.phase_offset(crop, points[:2]) is None
    flat = [(doy, 0.5) for doy in (130, 150, 170)]
    assert phenology.phase_offset(crop, flat) is None


def _plane_with_pit(n=60, res=2.0):
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    dem = 100 + 0.05 * x * res
    pit = (x - 30) ** 2 + (y - 30) ** 2 <= 16
    dem[pit] -= 0.8
    return dem, Affine(res, 0, 0, 0, -res, n * res)


def test_priority_flood_fills_pit_and_drains_everything():
    dem, transform = _plane_with_pit()
    flood = terrain.priority_flood(dem)
    assert (flood.filled >= dem - 1e-9).all()
    assert flood.order.size == dem.size
    acc = terrain.accumulation(flood, dem.shape)
    assert acc.max() > 100
    assert acc.sum() >= dem.size


def test_analyze_finds_depression_and_outflow():
    dem, transform = _plane_with_pit()
    parcel = box(20, 20, 100, 100)
    result = terrain.analyze(dem, transform, parcel, depth_threshold_m=0.15, min_depression_m2=20, channel_area_m2=400)
    assert len(result.depressions) == 1
    assert result.depressions[0]["max_depth_m"] == pytest.approx(0.75, abs=0.1)
    assert result.depression_volume_m3 > 0
    assert 0 < result.outflow_share < 1
    assert result.mean_slope_pct == pytest.approx(5.0, abs=0.6)
    assert terrain.runoff_risk(result.mean_slope_pct, result.flow_path_length_m) in ("średnia", "wysoka")


def test_runoff_risk_levels():
    assert terrain.runoff_risk(0.5, 0) == "niska"
    assert terrain.runoff_risk(2.5, 0) == "średnia"
    assert terrain.runoff_risk(6.0, 0) == "wysoka"


def test_landsat_qa_mask_rejects_fill_cloud_shadow_snow():
    from app.land.sources.landsat import valid_from_qa

    qa = np.array([0, 21824, 21826, 21888, 22280, 23888, 30048], dtype=np.uint16)
    assert valid_from_qa(qa).tolist() == [False, True, False, True, False, False, False]
