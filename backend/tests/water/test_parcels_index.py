import duckdb
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.core.config import get_settings
from app.core.main import create_app
from app.water import parcel as parcel_module
from app.water.geo import geom_to_4326
from app.water.sources import parcels_parquet, uldk

INDEXED = box(677000, 481500, 677200, 481650)
OTHER = box(700000, 500000, 700100, 500100)
INDEXED_ID = "143505_5.0001.1207/6"
MISSING_ID = "143505_5.0001.999"


def _write_index(folder, parcels):
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE p (id_dzialki VARCHAR, numer_dzialki VARCHAR, nazwa_obrebu VARCHAR, numer_obrebu VARCHAR, "
        "numer_jednostki VARCHAR, nazwa_gminy VARCHAR, data VARCHAR, xmin DOUBLE, ymin DOUBLE, xmax DOUBLE, "
        "ymax DOUBLE, geometry BLOB)"
    )
    for pid, number, geom in parcels:
        con.execute(
            "INSERT INTO p VALUES (?, ?, 'DESKURÓW', '1', '143505_5', 'WYSZKÓW - OBSZAR WIEJSKI', '2026-11-20', "
            "?, ?, ?, ?, ?)",
            [pid, number, *geom.bounds, geom.wkb],
        )
    con.execute(f"COPY p TO '{(folder / 'woj_14.parquet').as_posix()}' (FORMAT parquet)")


@pytest.fixture
def index(tmp_path, monkeypatch):
    _write_index(tmp_path, [(INDEXED_ID, "1207/6", INDEXED), ("143505_5.0001.1209/5", "1209/5", OTHER)])
    monkeypatch.setattr(get_settings(), "parcels_index_dir", tmp_path)
    return tmp_path


def _latlon(geom):
    point = geom_to_4326(geom.centroid)
    return point.y, point.x


def _uldk_row(pid, geom):
    return {"id": pid, "teryt": "143505_5", "commune": "Wyszków", "region": "Deskurów", "parcel": "999",
            "geom_wkt": geom.wkt}


async def test_index_finds_parcel_by_id_and_point(index):
    row = await parcels_parquet.index_by_id(INDEXED_ID)
    assert row["id"] == INDEXED_ID and row["parcel"] == "1207/6" and row["region"] == "DESKURÓW"
    assert row["commune"] == "WYSZKÓW - OBSZAR WIEJSKI" and row["teryt"] == "143505_5"
    assert await parcels_parquet.index_by_id(MISSING_ID) is None
    lat, lon = _latlon(INDEXED)
    assert (await parcels_parquet.index_by_point(lat, lon))["id"] == INDEXED_ID
    assert await parcels_parquet.index_by_point(52.0, 17.0) is None


async def test_resolve_uses_index_before_uldk(index, monkeypatch):
    async def forbidden(*args):
        raise AssertionError("ULDK nie powinno być pytane")

    monkeypatch.setattr(uldk, "by_id", forbidden)
    monkeypatch.setattr(uldk, "by_xy", forbidden)
    found, sources = await parcel_module.resolve_by_id(INDEXED_ID, with_land_use=False)
    assert found.source == parcels_parquet.INDEX_NAME and found.area_ha == pytest.approx(3.0)
    assert sources[0].name == parcels_parquet.INDEX_NAME and "woj_14.parquet" in sources[0].note
    assert "2026-11-20" in sources[0].note
    found, _ = await parcel_module.resolve_by_point(*_latlon(INDEXED), with_land_use=False)
    assert found.id == INDEXED_ID


async def test_parcel_missing_in_index_falls_back_to_uldk(index, monkeypatch):
    geom = box(690000, 490000, 690100, 490100)

    async def by_id(pid):
        return [_uldk_row(pid, geom)]

    async def by_xy(lat, lon):
        return [_uldk_row(MISSING_ID, geom)]

    monkeypatch.setattr(uldk, "by_id", by_id)
    monkeypatch.setattr(uldk, "by_xy", by_xy)
    found, sources = await parcel_module.resolve_by_id(MISSING_ID, with_land_use=False)
    assert found.source == "ULDK" and sources[0].name != parcels_parquet.INDEX_NAME
    found, _ = await parcel_module.resolve_by_point(*_latlon(geom), with_land_use=False)
    assert found.source == "ULDK"


def test_search_endpoint_suggests_parcels(index):
    client = TestClient(create_app())
    found = client.get("/api/parcels/search", params={"gmina": "wyszk", "numer": "1207"}).json()
    assert [p["id"] for p in found] == [INDEXED_ID]
    assert found[0]["obreb"] == "DESKURÓW" and found[0]["numer"] == "1207/6"
    assert len(client.get("/api/parcels/search", params={"gmina": "wyszk", "obreb": "desk"}).json()) == 2
    assert client.get("/api/parcels/search", params={"gmina": "wy"}).status_code == 422
    assert client.get("/api/parcels/search", params={"gmina": "wysz'; --"}).status_code == 422


def test_search_without_index_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "parcels_index_dir", tmp_path / "brak")
    response = TestClient(create_app()).get("/api/parcels/search", params={"gmina": "wyszk"})
    assert response.status_code == 503
