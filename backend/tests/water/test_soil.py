import pytest

from app.water.engine.soil_hydraulics import iung_category_from_texture, saxton_rawls, usda_texture
from app.water.engine.soil_water import taw_profile
from app.water.soil import layers_from_category, layers_from_soilgrids, summarize
from app.water.sources.soilgrids import parse_rest


def test_saxton_rawls_loam_matches_paper_table():
    fc, wp = saxton_rawls(40, 20, 2.5)
    assert fc == pytest.approx(0.28, abs=0.02)
    assert wp == pytest.approx(0.12, abs=0.02)


def test_sand_holds_less_water_than_loam():
    fc_s, wp_s = saxton_rawls(90, 3, 1.0)
    fc_l, wp_l = saxton_rawls(40, 20, 2.0)
    assert fc_s - wp_s < fc_l - wp_l


def test_more_organic_matter_more_water():
    a = saxton_rawls(60, 10, 1.0)
    b = saxton_rawls(60, 10, 2.0)
    assert b[0] - b[1] > a[0] - a[1]


@pytest.mark.parametrize(
    ("sand", "clay", "cat"),
    [(92, 2, "I"), (75, 7, "II"), (40, 15, "III"), (25, 30, "IV"), (10, 12, "III")],
)
def test_iung_category(sand, clay, cat):
    assert iung_category_from_texture(sand, clay) == cat


def test_texture_names():
    assert usda_texture(92, 5, 3) == "piasek"
    assert usda_texture(40, 40, 20) == "glina"


def test_parse_rest_converts_units():
    payload = {
        "properties": {
            "layers": [
                {"name": "sand", "depths": [{"label": "0-5cm", "values": {"mean": 650}}]},
                {"name": "clay", "depths": [{"label": "0-5cm", "values": {"mean": 120}}]},
                {"name": "soc", "depths": [{"label": "0-5cm", "values": {"mean": 150}}]},
            ]
        }
    }
    out = parse_rest(payload)
    assert out["0-5cm"] == {"sand": 65.0, "clay": 12.0, "soc": 1.5}


def test_layers_and_taw():
    raw = {
        f"{a}-{b}cm": {"sand": 70.0, "clay": 8.0, "soc": 1.0}
        for a, b in [(0, 5), (5, 15), (15, 30), (30, 60), (60, 100)]
    }
    layers = layers_from_soilgrids(raw)
    assert len(layers) == 5
    info = summarize(layers, "II", "test", "SoilGrids")
    assert info.awc_mm_100cm == pytest.approx(taw_profile(layers, 1.0), rel=1e-6)
    assert taw_profile(layers, 1.2) > taw_profile(layers, 1.0)


def test_category_defaults_ordered():
    awc = [summarize(layers_from_category(c), c, "t", "kategoria IUNG").awc_mm_100cm for c in ("I", "II", "III", "IV")]
    assert awc == sorted(awc)
