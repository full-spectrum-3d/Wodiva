from datetime import date

import httpx
import numpy as np
import pytest
import rasterio
import respx

from app.core.http import set_client
from app.land import service
from app.land.recommend import context
from app.land.sources import bdot, dem, pigpib

from .conftest import CROP, DAY


@pytest.fixture(autouse=True)
def fresh_client():
    set_client(None)
    yield
    set_client(None)


def test_parse_heights_skips_missing_and_zero_values():
    text = "528598.1 446603.3 92.1,528599.1 446603.3 0.0,528600.1 446603.3"
    assert dem.parse_heights(text) == {("528598.1", "446603.3"): 92.1}


@respx.mock
async def test_nmt_points_build_grid_in_batches_of_1000():
    seen = []

    def answer(request):
        body = httpx.QueryParams(request.content.decode())
        points = body["list"].split(",")
        seen.append(len(points))
        return httpx.Response(200, text=",".join(f"{p} {100 + i % 7}.5" for i, p in enumerate(points)))

    respx.post(dem.NMT_POINTS_URL).mock(side_effect=answer)
    transform = rasterio.Affine(3.0, 0, 446600.0, 0, -3.0, 528700.0)
    data = await dem._fetch_nmt_points(transform, 60, 40)
    assert data.shape == (40, 60) and np.isfinite(data).all()
    assert max(seen) <= dem.NMT_BATCH and sum(seen) == 2400


def test_fill_gaps_uses_nearest_value():
    data = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float32)
    filled = dem._fill_gaps(data)
    assert np.isfinite(filled).all() and filled[0, 1] in (1.0, 4.0)


def test_bdot_feature_info_parsing_keeps_mphp_id():
    xml = (
        '<FeatureInfoResponse><FIELDS OBJECTID="1" x_kod="SWKN01" idMPHP="188174" szerokosc="3" '
        'przebieg="ciek główny" x_aktualnoscG="2012-11-26" rodzaj="Null"/></FeatureInfoResponse>'
    )
    attributes = bdot.parse_feature_info(xml)
    item = bdot.describe("watercourse", attributes, 120.0)
    assert item["type"] == "kanał" and item["mphp_id"] == "188174" and item["width_m"] == 3.0
    assert "kind" not in item and item["distance_m"] == 120.0


def _well(depth, measured_ms, active="Tak"):
    return {
        "attributes": {
            "NR_PKT_MONIT_ILOSC": "II_1757_1",
            "MIEJSCOWOSC": "Balczewo",
            "AKTUALNIE_OBSERWOWANY": active,
            "CHARAKTER_PUNKTU": "Zwierciadło swobodne",
            "GLEBOKOSC_ZWIERCIADLA": depth,
            "DATA_POMIARU": measured_ms,
        },
        "geometry": {"x": 457058.6, "y": 546924.4},
    }


@respx.mock
async def test_pigpib_groundwater_respects_analysis_date():
    september_2026 = 1790719200000
    respx.get(url__regex=r".*/mwp/MapServer/0/query.*").mock(
        return_value=httpx.Response(200, json={"features": [_well(5.3, september_2026)]})
    )
    respx.get(url__regex=r".*/jcwpd/MapServer/5/query.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "features": [
                    {"attributes": {"KOD_UE": "PLGW600043", "STAN_ILOSCIOWY_2022": "słaby", "RYZYKO_2025": "zagrożona"}}
                ]
            },
        )
    )
    respx.get(url__regex=r".*/gzwp/MapServer/0/query.*").mock(
        return_value=httpx.Response(200, json={"features": [{"attributes": {"NAZWA": "Subzbiornik", "NR_GZWP": 143}}]})
    )
    from shapely.geometry import Point

    geom = Point(446603, 528598).buffer(50)
    past = await pigpib.groundwater(geom, date(2025, 7, 15))
    assert "water_table_depth_m" not in past["wells"][0]
    assert "measurement_after_analysis_date" in past["wells"][0]
    now = await pigpib.groundwater(geom, date(2026, 11, 21))
    assert now["wells"][0]["water_table_depth_m"] == 5.3
    assert now["body"]["quantitative_status"] == "słaby" and now["major_aquifer"]["number"] == 143
    assert pigpib.is_quantity_poor(now)
    old = await pigpib.groundwater(geom, date(2017, 7, 15))
    assert "quantitative_status" not in old["body"] and old["body"]["assessment_after_analysis_date"] == 2025
    assert not pigpib.is_quantity_poor(old)
    mid = await pigpib.groundwater(geom, date(2023, 7, 15))
    assert mid["body"]["quantitative_status"] == "słaby" and "risk" not in mid["body"]
    assert mid["body"]["assessment_after_analysis_date"] == 2025


def test_groundwater_drives_rule_and_irrigation_note(parcel, water, soil, irrigation, land):
    land.hydro.groundwater = {
        "wells": [],
        "body": {"code": "PLGW600043", "quantitative_status": "słaby", "risk": "zagrożona"},
    }
    observation = service.to_core(land)
    assert observation.hydro.groundwater["body"]["code"] == "PLGW600043"
    result = service.interpret(parcel, water, soil, irrigation, observation)
    titles = [r.title for r in result.recommendations]
    assert "Zasilaj wody podziemne retencją na działce" in titles
    ctx = context.build(CROP, DAY, True, parcel.area_ha, water, soil, irrigation, land, [], None)
    assert ctx["gw_quantity_poor"] is True


def test_watercourse_attributes_reach_core_hydro(land):
    land.hydro.watercourse_distance_m = 120.0
    land.hydro.features = [
        {"group": "watercourse", "type": "kanał", "mphp_id": "188174", "distance_m": 120.0, "source": "BDOT10k"}
    ]
    hydro = service.to_core(land).hydro
    assert hydro.watercourses[0]["mphp_id"] == "188174"
    assert hydro.ditches[0]["distance_m"] == 60
