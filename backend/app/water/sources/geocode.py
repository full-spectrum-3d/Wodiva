import re
from datetime import UTC, datetime

from app.core.cache import get_cache
from app.core.http import SourceError, fetch
from app.core.schemas import DataSource, SourceStatus

URL = "https://services.gugik.gov.pl/uug/"
STREET_PREFIX = re.compile(r"^(ul\.?|ulica|al\.?|aleja|pl\.?|plac|os\.?|osiedle)\s+", re.IGNORECASE)


class AddressNotFound(Exception):
    pass


def data_source(status: SourceStatus = SourceStatus.ok, note: str | None = None) -> DataSource:
    return DataSource(
        name="UUG GUGiK – usługa geokodowania adresów (PRG)",
        url="https://services.gugik.gov.pl/uug/",
        license="Dane publiczne GUGiK, bezpłatne",
        retrieved_at=datetime.now(UTC),
        status=status,
        note=note,
    )


def query_text(city: str, street: str, number: str) -> str:
    street = STREET_PREFIX.sub("", street.strip())
    return f"{city}, {street} {number}" if street else f"{city}, {number}"


def _unit(raw: str | None) -> list[str]:
    return [part.strip().strip('"') for part in (raw or "").strip("{}").split(",")]


def parse(payload: dict) -> list[dict]:
    found = []
    for item in (payload.get("results") or {}).values():
        try:
            x, y = float(item["x"]), float(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        unit = _unit(item.get("jednostka"))
        found.append(
            {
                "city": item.get("city"),
                "street": item.get("street"),
                "number": item.get("number"),
                "voivodeship": unit[1] if len(unit) > 1 else None,
                "county": unit[2] if len(unit) > 2 else None,
                "commune": unit[3] if len(unit) > 3 else None,
                "x": x,
                "y": y,
            }
        )
    return found


def label(address: dict) -> str:
    if address.get("street"):
        place = f"{address['street']} {address['number']}, {address['city']}"
    else:
        place = f"{address['city']} {address['number']}"
    return f"{place}, gm. {address['commune']}" if address.get("commune") else place


async def addresses(city: str, street: str, number: str) -> list[dict]:
    text = query_text(city, street, number)

    async def run():
        response = await fetch("uug", URL, params={"request": "GetAddress", "address": text}, retries=1)
        try:
            return parse(response.json())
        except ValueError as exc:
            raise SourceError("uug", "niepoprawna odpowiedź") from exc

    try:
        return await get_cache().get_or_fetch("uug", (text.lower(),), run)
    except SourceError as exc:
        raise AddressNotFound(f"usługa adresów GUGiK nie odpowiada ({exc})") from exc
