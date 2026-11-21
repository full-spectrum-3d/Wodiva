from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.http import set_client
from app.core.main import create_app
from app.water import meteo
from app.water.sources import era5, imgw


@pytest.fixture(autouse=True)
def fresh_client():
    set_client(None)
    yield
    set_client(None)


def test_health_hides_disk_path_and_cors_is_off_by_default(monkeypatch):
    monkeypatch.setattr(get_settings(), "cors_origins", "")
    client = TestClient(create_app())
    response = client.get("/api/health", headers={"Origin": "https://example.org"})
    assert "path" not in response.json()["era5_cube"]
    assert "access-control-allow-origin" not in response.headers


def test_cors_only_for_configured_origin(monkeypatch):
    monkeypatch.setattr(get_settings(), "cors_origins", "https://wodiva.example")
    client = TestClient(create_app())
    allowed = client.get("/api/health", headers={"Origin": "https://wodiva.example"})
    other = client.get("/api/health", headers={"Origin": "https://example.org"})
    assert allowed.headers["access-control-allow-origin"] == "https://wodiva.example"
    assert "access-control-allow-origin" not in other.headers


def test_assistant_and_report_routers_are_mounted():
    paths = set(create_app().openapi()["paths"])
    assert "/api/assistant" in paths and "/api/report/{report_id}" in paths


@respx.mock
async def test_filled_days_are_marked(cube_path, analysis_day, monkeypatch):
    respx.get(url__startswith=imgw.ARCHIVE).mock(return_value=httpx.Response(404))
    real = era5.point_series
    gap = analysis_day - timedelta(days=3)

    def with_gap(*args):
        return real(*args).drop(index=gap)

    monkeypatch.setattr(era5, "point_series", with_gap)
    result = await meteo.load(51.2, 21.2, analysis_day, 10)
    sources = {d.date: d.source for d in result.series.days}
    assert sources[gap] == "uzupełnione" and sources[analysis_day] == "era5"
    assert any(lim.code == "meteo_gaps" for lim in result.limitations)
