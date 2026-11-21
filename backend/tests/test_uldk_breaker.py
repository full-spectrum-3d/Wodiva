import httpx
import pytest
import respx

from app.core.http import set_client
from app.water.sources import uldk


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    set_client(None)
    monkeypatch.setattr(uldk, "_blocked_until", 0.0)  # monkeypatch przywraca stan po teście
    yield
    set_client(None)


@respx.mock
async def test_429_blocks_uldk_without_retry():
    route = respx.get(uldk.URL).mock(return_value=httpx.Response(429))
    with pytest.raises(uldk.ParcelNotFound, match="429"):
        await uldk.by_id("141201_1.0001.6509")
    assert route.call_count == 1  # bez ponowień
    with pytest.raises(uldk.ParcelNotFound, match="blokuje"):
        await uldk.by_id("141201_1.0001.6510")
    assert route.call_count == 1  # bezpiecznik: kolejne zapytanie nie idzie do ULDK


@respx.mock
async def test_redirect_to_other_host_blocks_uldk():
    respx.get(uldk.URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://integracja01.gugik.gov.pl/resp/x.php"})
    )
    respx.get("https://integracja01.gugik.gov.pl/resp/x.php").mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(uldk.ParcelNotFound, match="przekierowanie"):
        await uldk.by_xy(51.42, 21.97)
    with pytest.raises(uldk.ParcelNotFound, match="blokuje"):
        await uldk.by_xy(51.43, 21.98)
