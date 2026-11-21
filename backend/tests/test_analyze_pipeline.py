import time

import httpx
import pytest
import respx

from app.core.api.analyze import run_analysis
from app.core.dates import assert_not_after
from app.core.http import set_client
from app.core.schemas import AnalyzeRequest
from app.water.geo import lonlat_to_2180
from app.water.sources import egib, imgw, soilgrids, uldk

DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]


def _uldk_text() -> str:
    x, y = lonlat_to_2180(21.25, 51.25)
    wkt = f"SRID=2180;POLYGON(({x} {y},{x + 150} {y},{x + 150} {y + 120},{x} {y + 120},{x} {y}))"
    return f"0\n141201_1.0001.6509|141201_1|mazowieckie|p|g|o|6509|{wkt}\n"


def _soil_payload():
    values = {"sand": 700, "clay": 80, "soc": 90}
    return {
        "properties": {
            "layers": [
                {"name": k, "depths": [{"label": d, "values": {"mean": v}} for d in DEPTHS]} for k, v in values.items()
            ]
        }
    }


@pytest.fixture(autouse=True)
def fresh_client():
    set_client(None)
    yield
    set_client(None)


@respx.mock
async def test_full_analysis_historical(cube_path, analysis_day):
    respx.get(uldk.URL).mock(return_value=httpx.Response(200, text=_uldk_text()))
    respx.get(egib.URL).mock(return_value=httpx.Response(200, text="<td>R IVb</td>"))
    respx.get(soilgrids.REST_URL).mock(return_value=httpx.Response(200, json=_soil_payload()))
    respx.get(url__startswith=imgw.ARCHIVE).mock(return_value=httpx.Response(404))
    started = time.perf_counter()
    report = await run_analysis(
        AnalyzeRequest(parcel_id="141201_1.0001.6509", date=analysis_day, crop="pszenica_ozima")
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 10
    assert report.parcel.is_agricultural is True
    assert report.soil.iung_category == "II"
    assert report.water.soil_water.date == analysis_day
    assert_not_after(report.water.meteo_last_90, analysis_day)
    assert report.water.forecast == []
    assert report.water.climate.kbw_threshold_mm is not None
    assert report.irrigation is not None
    names = {s.name.split(" ")[0] for s in report.sources}
    assert {"ULDK", "ERA5-Land", "ISRIC", "IUNG-PIB", "EGiB"} <= names
    assert "total" in report.timings_s
    assert any(lim.code in ("land_missing", "satellite_missing") for lim in report.limitations)


@respx.mock
async def test_full_analysis_early_date_flags_short_history(cube_path):
    respx.get(uldk.URL).mock(return_value=httpx.Response(200, text=_uldk_text()))
    respx.get(egib.URL).mock(return_value=httpx.Response(200, text="<td>R IVb</td>"))
    respx.get(soilgrids.REST_URL).mock(return_value=httpx.Response(200, json=_soil_payload()))
    respx.get(url__startswith=imgw.ARCHIVE).mock(return_value=httpx.Response(404))
    report = await run_analysis(AnalyzeRequest(parcel_id="141201_1.0001.6509", date="2016-12-01", crop="rzepak_ozimy"))
    assert any(lim.code == "history_short" for lim in report.limitations)
    assert report.irrigation.status == "nie dotyczy"
