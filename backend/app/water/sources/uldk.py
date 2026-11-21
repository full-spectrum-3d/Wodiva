import time
from datetime import UTC, datetime

from app.core.cache import get_cache
from app.core.http import SourceError, fetch
from app.core.schemas import DataSource, SourceStatus
from app.water.geo import lonlat_to_2180

URL = "https://uldk.gugik.gov.pl/"
# Po blokadzie (429 albo przekierowanie na inny host) nie pytamy ULDK przez 10 min: kolejne zapytania
# przedłużają blokadę, a rolnik od razu dostaje zapas (eksport EGiB) zamiast czekać na ponowienia.
BLOCK_S = 600
_blocked_until = 0.0
URL_HOST = "uldk.gugik.gov.pl"
FIELDS = ["id", "teryt", "voivodeship", "county", "commune", "region", "parcel", "geom_wkt"]


class ParcelNotFound(Exception):
    pass


def data_source(status: SourceStatus = SourceStatus.ok, note: str | None = None) -> DataSource:
    return DataSource(
        name="ULDK GUGiK – usługa lokalizacji działek katastralnych",
        url="https://uldk.gugik.gov.pl/opis.html",
        license="Dane publiczne GUGiK, bezpłatne (ustawa Prawo geodezyjne i kartograficzne)",
        retrieved_at=datetime.now(UTC),
        status=status,
        note=note,
    )


def parse_response(text: str) -> list[dict]:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise ParcelNotFound("pusta odpowiedź ULDK")
    head = lines[0]
    if head.startswith("-1"):
        raise ParcelNotFound(head.split(" ", 1)[-1] if " " in head else "brak działki")
    rows = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < len(FIELDS):
            continue
        row = dict(zip(FIELDS, parts[: len(FIELDS)], strict=True))
        if row["geom_wkt"]:
            rows.append(row)
    if not rows:
        raise ParcelNotFound("ULDK nie zwróciło geometrii")
    return rows


async def _query(request: str, key: str, extra: dict) -> list[dict]:
    global _blocked_until

    async def run():
        if time.monotonic() < _blocked_until:
            raise SourceError("uldk", "usługa blokuje zapytania, ponowimy za kilka minut")
        params = {"request": request, "result": ",".join(FIELDS), "srid": "2180", **extra}
        response = await fetch("uldk", URL, params=params)
        if response.url.host != URL_HOST:
            raise SourceError("uldk", f"przekierowanie na {response.url.host}")
        return parse_response(response.text)

    try:
        return await get_cache().get_or_fetch("uldk", (request, key), run)
    except SourceError as exc:
        if "429" in str(exc) or "przekierowanie" in str(exc):
            _blocked_until = time.monotonic() + BLOCK_S
        raise ParcelNotFound(f"ULDK niedostępne ({exc})") from exc


async def by_id(parcel_id: str) -> list[dict]:
    request = "GetParcelById" if "_" in parcel_id and "." in parcel_id else "GetParcelByIdOrNr"
    return await _query(request, parcel_id, {"id": parcel_id})


async def by_xy(lat: float, lon: float) -> list[dict]:
    x, y = lonlat_to_2180(lon, lat)
    return await _query("GetParcelByXY", f"{x:.1f},{y:.1f}", {"xy": f"{x:.2f},{y:.2f},2180"})
