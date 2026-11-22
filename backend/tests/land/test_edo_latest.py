from datetime import date

import httpx
import pytest
import respx

from app.land.sources import edo

CAPS = '<Layer><Name>cdiad</Name><Dimension name="time">2012-01-01/2026-11-01/P10D</Dimension></Layer>'


@respx.mock
async def test_cdi_asks_for_latest_published_dekad(monkeypatch):
    monkeypatch.setattr(edo.cache, "get", lambda key: None)
    monkeypatch.setattr(edo.cache, "set", lambda *args: None)
    seen = []

    def handler(request):
        if request.url.params.get("REQUEST") == "GetCapabilities":
            return httpx.Response(200, text=CAPS)
        seen.append(request.url.params.get("TIME"))
        return httpx.Response(400)

    respx.get(url__startswith=edo.WMS_URL).mock(side_effect=handler)
    assert await edo.latest_published() == date(2026, 11, 1)
    with pytest.raises(httpx.HTTPStatusError):
        await edo.cdi(21.0, 52.2, date(2026, 11, 22))
    assert seen == ["2026-11-01"]
    with pytest.raises(httpx.HTTPStatusError):
        await edo.cdi(21.0, 52.2, date(2025, 6, 20))
    assert seen[-1] == "2025-06-11"
