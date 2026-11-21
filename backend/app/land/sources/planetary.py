from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from app.land.cache import DAY, cache
from app.land.net import client
from app.land.settings import land_settings

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"

_tokens: dict[str, tuple[str, float]] = {}


async def sas_token(collection: str) -> str:
    cached = _tokens.get(collection)
    if cached is not None and cached[1] > time.time() + 300:
        return cached[0]
    response = await client().get(TOKEN_URL.format(collection=collection), timeout=land_settings().source_timeout_s)
    response.raise_for_status()
    payload = response.json()
    expiry = datetime.fromisoformat(payload["msft:expiry"].replace("Z", "+00:00")).timestamp()
    _tokens[collection] = (payload["token"], expiry)
    return payload["token"]


def epsg(item: dict) -> int:
    props = item["properties"]
    if "proj:epsg" in props:
        return int(props["proj:epsg"])
    return int(str(props["proj:code"]).split(":")[1])


async def search(
    collection: str, bbox, start: date, end: date, assets: tuple[str, ...], limit: int = 40, query: dict | None = None
) -> list[dict]:
    key = cache.make_key("pcsearch", collection, bbox, str(start), str(end), assets, limit, query)
    cached = cache.get(key)
    if cached is not None:
        return cached
    body = {
        "collections": [collection],
        "bbox": list(bbox),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": limit,
    }
    if query:
        body["query"] = query
    response = await client().post(STAC_URL, json=body, timeout=land_settings().source_timeout_s)
    response.raise_for_status()
    items = [
        {
            "id": f["id"],
            "geometry": f["geometry"],
            "properties": f["properties"],
            "assets": {k: f["assets"][k] for k in assets if k in f["assets"]},
        }
        for f in response.json().get("features", [])
    ]
    ttl = 30 * DAY if end < date.today() - timedelta(days=30) else DAY / 4
    cache.set(key, items, ttl)
    return items
