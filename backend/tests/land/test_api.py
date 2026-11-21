import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.api.analyze import run_analysis
from app.core.http import set_client
from app.core.main import create_app
from app.core.schemas import AnalyzeRequest
from app.land import service
from app.water.geo import lonlat_to_2180
from app.water.sources import egib, imgw, soilgrids, uldk

DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]


def _uldk_text() -> str:
    x, y = lonlat_to_2180(21.25, 51.25)
    wkt = f"SRID=2180;POLYGON(({x} {y},{x + 150} {y},{x + 150} {y + 120},{x} {y + 120},{x} {y}))"
    return f"0\n141201_1.0001.6509|141201_1|mazowieckie|p|g|o|6509|{wkt}\n"


def _soil_payload():
    values = {"sand": 700, "clay": 80, "soc": 90}
    layers = [{"name": k, "depths": [{"label": d, "values": {"mean": v}} for d in DEPTHS]} for k, v in values.items()]
    return {"properties": {"layers": layers}}


@pytest.fixture(autouse=True)
def fresh_client():
    set_client(None)
    yield
    set_client(None)


@respx.mock
async def test_analyze_runs_through_land_and_report(cube_path, analysis_day, monkeypatch, land, artifacts):
    async def fake_collect(*args):
        return land, artifacts

    monkeypatch.setattr(service.collect, "collect", fake_collect)
    respx.get(uldk.URL).mock(return_value=httpx.Response(200, text=_uldk_text()))
    respx.get(egib.URL).mock(return_value=httpx.Response(200, text="<td>R IVb</td>"))
    respx.get(soilgrids.REST_URL).mock(return_value=httpx.Response(200, json=_soil_payload()))
    respx.get(url__startswith=imgw.ARCHIVE).mock(return_value=httpx.Response(404))
    report = await run_analysis(
        AnalyzeRequest(parcel_id="141201_1.0001.6509", date=analysis_day, crop="pszenica_ozima")
    )
    assert report.terrain.slope_mean_pct == 3.4
    assert report.satellite.phase_offset_days == 6
    assert report.recommendations and report.confidence
    assert not any(lim.code == "land_missing" for lim in report.limitations)
    assert any(s.name.startswith("BDOT10k") for s in report.sources)

    client = TestClient(create_app())
    assert client.get(f"/api/report/{report.id}").json()["id"] == report.id
    assert client.get(f"/api/report/{report.id}.pdf").content[:4] == b"%PDF"
    assert client.get(f"/api/report/{report.id}/summary").json()["headline"]
    assert client.get(f"/api/report/{report.id}/map.png").status_code == 200
    answer = client.post("/api/assistant", json={"report_id": report.id, "question": "Co zrobić najpierw?"})
    assert answer.status_code == 200 and answer.json()["answer"]
    assert client.get("/api/assistant/questions").json()
    assert client.get("/api/evidence").text.startswith("# Rejestr")


def test_unknown_report_is_404():
    client = TestClient(create_app())
    assert client.get("/api/report/../../etc").status_code == 404
    assert client.get("/api/report/0123456789ab").status_code == 404
    assert client.post("/api/assistant", json={"report_id": "zzz", "question": "a"}).status_code == 404
