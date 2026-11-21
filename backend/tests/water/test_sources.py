import io
import zipfile
from datetime import date

import httpx
import numpy as np
import pytest
import respx
import xarray as xr

from app.core.http import set_client
from app.core.validation import InputError, normalize_parcel_id
from app.water.parcel import ParcelLookupError, build_parcel, resolve_by_id
from app.water.sources import egib, era5, imgw, openmeteo, uldk

WKT = "SRID=2180;POLYGON((745000 370000,745200 370000,745200 370150,745000 370150,745000 370000))"
ULDK_OK = f"0\n141201_1.0001.6509|141201_1|mazowieckie|miński|Mińsk|Mińsk|6509|{WKT}\n"


@pytest.fixture(autouse=True)
def fresh_client():
    set_client(None)
    yield
    set_client(None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("141201_1.0001.6509", "141201_1.0001.6509"),
        (" 141201_1.0001.6509 ", "141201_1.0001.6509"),
        ("141201_1.1.6509", "141201_1.0001.6509"),
        ("141201_1.0001.AR_2.12/3", "141201_1.0001.AR_2.12/3"),
        ("141201_1.0001.ar2.12/3", "141201_1.0001.AR_2.12/3"),
        ("Krzewina 134", "Krzewina 134"),
    ],
)
def test_normalize_parcel_id(raw, expected):
    assert normalize_parcel_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "14120_1.0001.6509", "'; DROP TABLE"])
def test_reject_bad_ids(raw):
    with pytest.raises(InputError):
        normalize_parcel_id(raw)


def test_uldk_parse_ok_and_error():
    rows = uldk.parse_response(ULDK_OK)
    assert rows[0]["teryt"] == "141201_1" and rows[0]["geom_wkt"].startswith("SRID")
    with pytest.raises(uldk.ParcelNotFound):
        uldk.parse_response("-1 brak wyników\n")


def test_build_parcel_area_and_flags():
    p = build_parcel(uldk.parse_response(ULDK_OK)[0], "ULDK")
    assert p.area_ha == pytest.approx(3.0)
    assert p.size_class == "średnia"
    assert 51 < p.centroid_lat < 53 and 20 < p.centroid_lon < 24
    assert p.geometry_geojson["type"] == "Polygon"


@respx.mock
async def test_resolve_by_id_with_land_use():
    respx.get(uldk.URL).mock(return_value=httpx.Response(200, text=ULDK_OK))
    respx.get(egib.URL).mock(return_value=httpx.Response(200, text="<table><tr><td>R</td><td>RIVa</td></tr></table>"))
    parcel, sources = await resolve_by_id("141201_1.0001.6509")
    assert parcel.id == "141201_1.0001.6509"
    assert parcel.is_agricultural is True
    assert parcel.land_use[0].code == "R"
    assert {s.status for s in sources} == {"ok"}


@respx.mock
async def test_resolve_falls_back_to_parquet(monkeypatch):
    respx.get(uldk.URL).mock(return_value=httpx.Response(500))

    async def fake(pid):
        return {"id": pid, "teryt": "141201_1", "parcel": "6509", "geom_wkt": WKT}

    monkeypatch.setattr("app.water.parcel.parcels_parquet.by_id", fake)
    parcel, sources = await resolve_by_id("141201_1.0001.6509", with_land_use=False)
    assert parcel.source == "EGiB parquet"
    assert sources[0].status == "brak"


@respx.mock
async def test_resolve_ambiguous_name():
    two = ULDK_OK + f"141201_1.0002.134|141201_1|m|p|g|Inna|134|{WKT}\n"
    respx.get(uldk.URL).mock(return_value=httpx.Response(200, text=two))
    with pytest.raises(ParcelLookupError) as exc:
        await resolve_by_id("Krzewina 134", with_land_use=False)
    assert len(exc.value.candidates) == 2


def test_egib_parse_and_agricultural():
    html = "<tr><td>Ps</td><td>Ps III</td><td>W</td><td>Wody</td></tr>"
    assert egib.parse_feature_info(html) == [("Ps", None), ("Ps", "III"), ("W", None)]
    assert egib.is_agricultural([]) is None


def _imgw_zip(code: str, year: int) -> bytes:
    lines = []
    for day in range(1, 32):
        lines.append(
            f'"35220{code}","STACJA","{year}","7","{day}","25.0","","15.0","","20.0","","10.0","",'
            f'"{2.5 if day % 3 else 0}","{"" if day % 3 else "9"}",""'
        )
    lines.append(f'"35220{code}","STACJA","{year}","7","5","25.0","8","15.0","","20.0","","10.0","","1.0","8",""')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"s_d_{code}_{year}.csv", "\n".join(lines).encode("cp1250"))
        zf.writestr(f"s_d_t_{code}_{year}.csv", "ignored")
    return buf.getvalue()


def test_imgw_parse_zip_status_codes():
    frame = imgw.parse_archive_zip(_imgw_zip("375", 2024), "375")
    assert len(frame) == 31
    assert frame.loc[date(2024, 7, 3), "precip_mm"] == 0.0
    assert frame.loc[date(2024, 7, 1), "precip_mm"] == 2.5


def test_imgw_nearest_skips_mountains():
    station, km = imgw.nearest(49.24, 19.98)
    assert station.name not in {"Kasprowy Wierch", "Zakopane"}
    assert imgw.nearest(52.2, 21.0)[0].name == "Warszawa"


def test_imgw_archive_file_names():
    st = next(s for s in imgw.stations() if s.code == "375")
    files = imgw.archive_files(st, date(2024, 11, 1), date(2025, 2, 1))
    assert files[0] == "2024/2024_375_s.zip"


def test_openmeteo_hourly_to_daily():
    hours = [f"2024-07-{d:02d}T{h:02d}:00" for d in (1, 2) for h in range(24)]
    payload = {
        "hourly": {
            "time": hours,
            "temperature_2m": [10 + (h % 24) * 0.5 for h in range(48)],
            "dew_point_2m": [8.0] * 48,
            "precipitation": [0.5] * 48,
            "shortwave_radiation": [250.0] * 48,
            "wind_speed_10m": [3.0] * 48,
            "surface_pressure": [1000.0] * 48,
        }
    }
    daily = openmeteo.hourly_to_daily(payload)
    assert len(daily) == 2
    row = daily.iloc[0]
    assert row["precip_mm"] == pytest.approx(12.0)
    assert row["rs_mj"] == pytest.approx(250 * 24 * 3600 / 1e6)
    assert row["pressure_kpa"] == pytest.approx(100.0)
    assert row["tmax_c"] == pytest.approx(21.5)


def test_era5_point_series_interpolates_and_truncates(cube_path):
    ds = xr.open_zarr(cube_path)
    frame = era5.point_series(51.25, 21.25, date(2020, 1, 1), date(2024, 7, 15), ds)
    assert max(frame.index) == date(2024, 7, 15)
    assert frame["wind10_ms"].iloc[0] == pytest.approx(3.0)
    corner = era5.point_series(51.02, 21.02, date(2020, 1, 1), date(2020, 1, 10), ds)
    assert not np.isnan(corner["precip_mm"]).any()
    assert era5.cell_id(51.234, 21.27) == "51.2_21.3"
