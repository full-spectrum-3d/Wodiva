from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.main import create_app
from app.core.security import RateLimitMiddleware


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and "era5_cube" in body


def test_crops(client):
    crops = client.get("/api/crops").json()
    codes = {c["code"] for c in crops}
    assert {"pszenica_ozima", "kukurydza_ziarno", "uzytki_zielone"} <= codes


def test_mock_report_full_order(client):
    r = client.post("/api/analyze?mock=true", json={"parcel_id": "mock", "date": "2025-07-01", "crop": "ziemniak"})
    assert r.status_code == 200
    rep = r.json()
    assert rep["mock"] is True
    assert rep["water"]["soil_water"]["in_season"] is True
    assert rep["irrigation"]["status"] in {"zalecane", "niezalecane", "monitoruj"}
    assert len(rep["water"]["scenarios"]) == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"parcel_id": "141201_1.0001.6509", "date": (date.today() + timedelta(days=1)).isoformat(), "crop": "ziemniak"},
        {"parcel_id": "141201_1.0001.6509", "date": "2010-05-01", "crop": "ziemniak"},
        {"parcel_id": "141201_1.0001.6509", "date": "2024-05-01", "crop": "banan"},
        {"parcel_id": "zly identyfikator!!", "date": "2024-05-01", "crop": "ziemniak"},
    ],
)
def test_analyze_rejects_bad_input(client, payload):
    assert client.post("/api/analyze", json=payload).status_code == 422


def test_parcel_requires_params(client):
    assert client.get("/api/parcel").status_code == 422
    assert client.get("/api/parcel?lat=40&lon=10").status_code == 422


def test_rate_limit():
    app = create_app()
    app.user_middleware.clear()
    app.add_middleware(RateLimitMiddleware, per_minute=2)
    c = TestClient(app)
    codes = [c.get("/api/parcel").status_code for _ in range(3)]
    assert codes[-1] == 429
