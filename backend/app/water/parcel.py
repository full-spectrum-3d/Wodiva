import asyncio
import logging
import re
import unicodedata

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from app.core.schemas import DataSource, Parcel, SourceStatus
from app.core.validation import InputError, is_full_parcel_id, normalize_parcel_id, validate_lat_lon
from app.water.geo import count_parts, geojson_4326, geom_to_4326, parse_wkt, reproject, to_2180
from app.water.sources import egib, geocode, parcels_parquet, uldk

log = logging.getLogger("wodiva.parcel")

SMALL_HA = 1.0
LARGE_HA = 50.0
MAX_CANDIDATES = 8
REGION_QUERY = re.compile(
    r"^(?:(?P<commune>[^,\d][^,]*?)\s*,\s*)?(?P<region>[^\W\d_][\w .\-]*?)\s+(?P<number>\d{1,6}(?:/\d{1,4})?)$"
)


class ParcelLookupError(Exception):
    def __init__(self, message: str, candidates: list[dict] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


def size_class(area_ha: float) -> str:
    if area_ha < SMALL_HA:
        return "mała"
    if area_ha > LARGE_HA:
        return "duża"
    return "średnia"


def _ensure_2180(geom: BaseGeometry) -> BaseGeometry:
    minx, miny, _, _ = geom.bounds
    if abs(minx) <= 180 and abs(miny) <= 90:
        return reproject(geom, to_2180())
    return geom


def build_parcel(row: dict, source: str) -> Parcel:
    geom = _ensure_2180(parse_wkt(row["geom_wkt"]))
    centroid = geom_to_4326(geom.centroid)
    area_ha = geom.area / 10000
    flags = []
    parts = count_parts(geom)
    if parts > 1:
        flags.append("wieloczęściowa")
    cls = size_class(area_ha)
    if cls == "mała":
        flags.append("mała działka – mało pikseli satelitarnych")
    if cls == "duża":
        flags.append("duża działka – możliwa duża zmienność wewnątrz")
    return Parcel(
        id=row.get("id") or "",
        teryt=row.get("teryt") or None,
        voivodeship=row.get("voivodeship") or None,
        county=row.get("county") or None,
        commune=row.get("commune") or None,
        region=row.get("region") or None,
        number=row.get("parcel") or None,
        geometry_wkt_2180=geom.wkt,
        geometry_geojson=geojson_4326(geom),
        area_ha=round(area_ha, 4),
        perimeter_m=round(geom.length, 1),
        centroid_lat=round(centroid.y, 6),
        centroid_lon=round(centroid.x, 6),
        parts=parts,
        size_class=cls,
        flags=flags,
        source=source,
    )


async def _with_land_use(parcel: Parcel, sources: list[DataSource], codes: str | None = None) -> Parcel:
    shares = egib.shares_from_codes(codes)
    if shares:
        sources.append(egib.index_source(codes or ""))
        checked = True
    else:
        shares, ds = await egib.land_use(parse_wkt(parcel.geometry_wkt_2180))
        sources.append(ds)
        checked = ds.note != egib.UNAVAILABLE
    parcel.land_use = shares
    parcel.land_use_checked = checked
    parcel.is_agricultural = egib.is_agricultural(shares)
    if parcel.is_agricultural is False:
        parcel.flags.append("działka nierolnicza wg EGiB")
    return parcel


def _candidates(rows: list[dict]) -> list[dict]:
    return [
        {"id": r["id"], "commune": r.get("commune"), "region": r.get("region"), "county": r.get("county")}
        for r in rows[:20]
    ]


def _fold(text: str | None) -> str:
    plain = unicodedata.normalize("NFKD", (text or "").lower().replace("ł", "l"))
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(plain.replace("-", " ").split())


def _same_place(name: str | None, wanted: str) -> bool:
    folded = _fold(wanted)
    return not folded or _fold(name).startswith(folded)


async def _from_index(lookup, *args) -> dict | None:
    if parcels_parquet.index_dir() is None:
        return None
    try:
        return await lookup(*args)
    except Exception as exc:
        log.warning("local parcel index failed: %s", exc)
        return None


def _indexed(row: dict, sources: list[DataSource]) -> Parcel:
    sources.append(parcels_parquet.index_source(row))
    return build_parcel(row, parcels_parquet.INDEX_NAME)


async def _remote_by_id(parcel_id: str, sources: list[DataSource]) -> Parcel:
    try:
        rows = await uldk.by_id(parcel_id)
        if len(rows) > 1 and not is_full_parcel_id(parcel_id):
            raise ParcelLookupError("Znaleziono kilka działek – wybierz właściwą.", _candidates(rows))
        sources.append(uldk.data_source())
        return build_parcel(rows[0], "ULDK")
    except uldk.ParcelNotFound as exc:
        sources.append(uldk.data_source(SourceStatus.missing, str(exc)))
        if not is_full_parcel_id(parcel_id):
            raise ParcelLookupError(f"Nie znaleziono działki: {exc}") from exc
        try:
            row = await parcels_parquet.by_id(parcel_id)
        except Exception as pexc:
            log.warning("parquet fallback failed: %s", pexc)
            row = None
        if row is None:
            raise ParcelLookupError(f"Nie znaleziono działki {parcel_id} (ULDK i EGiB parquet).") from exc
        sources.append(parcels_parquet.data_source(parcel_id=parcel_id))
        return build_parcel(row, "EGiB parquet")


async def resolve_by_id(raw_id: str, with_land_use: bool = True) -> tuple[Parcel, list[DataSource]]:
    typed = REGION_QUERY.match(raw_id.strip())
    if typed:
        return await resolve_by_region(typed["region"], typed["number"], typed["commune"] or "", with_land_use)
    parcel_id = normalize_parcel_id(raw_id)
    sources: list[DataSource] = []
    row = await _from_index(parcels_parquet.index_by_id, parcel_id) if is_full_parcel_id(parcel_id) else None
    parcel = _indexed(row, sources) if row is not None else await _remote_by_id(parcel_id, sources)
    if with_land_use:
        parcel = await _with_land_use(parcel, sources, row.get("land_codes") if row else None)
    return parcel, sources


async def resolve_by_point(lat: float, lon: float, with_land_use: bool = True) -> tuple[Parcel, list[DataSource]]:
    validate_lat_lon(lat, lon)
    sources: list[DataSource] = []
    row = await _from_index(parcels_parquet.index_by_point, lat, lon)
    if row is not None:
        parcel = _indexed(row, sources)
    else:
        try:
            rows = await uldk.by_xy(lat, lon)
        except uldk.ParcelNotFound as exc:
            raise ParcelLookupError(f"Nie znaleziono działki w tym miejscu: {exc}") from exc
        parcel = build_parcel(rows[0], "ULDK")
        sources.append(uldk.data_source())
    if with_land_use:
        parcel = await _with_land_use(parcel, sources, row.get("land_codes") if row else None)
    return parcel, sources


async def _indexed_matches(region: str, number: str, commune: str) -> list[dict]:
    if not commune or parcels_parquet.index_dir() is None:
        return []
    try:
        rows = await parcels_parquet.search(commune, region, number, 20)
    except Exception as exc:
        log.warning("local parcel search failed: %s", exc)
        return []
    return [
        {"id": r["id"], "commune": r["gmina"], "region": r["obreb"], "county": None}
        for r in rows
        if r["numer"] == number and _fold(r["obreb"]) == _fold(region)
    ]


async def _uldk_matches(region: str, number: str, commune: str) -> list[dict]:
    try:
        regions = await uldk.regions(region)
    except uldk.ParcelNotFound as exc:
        raise ParcelLookupError(f"Nie znaleziono obrębu „{region}”: {exc}") from exc
    regions = [r for r in regions if _same_place(r.get("commune"), commune)]
    if not regions:
        raise ParcelLookupError(f"W gminie {commune} nie ma obrębu „{region}”. Sprawdź nazwy w wypisie z ewidencji.")
    found = await asyncio.gather(
        *[uldk.by_id(f"{r['teryt']}.{number}") for r in regions[:MAX_CANDIDATES]], return_exceptions=True
    )
    return [rows[0] for rows in found if isinstance(rows, list) and rows]


async def resolve_by_region(
    region: str, number: str, commune: str = "", with_land_use: bool = True
) -> tuple[Parcel, list[DataSource]]:
    region, number, commune = region.strip(), number.strip(), commune.strip()
    if not region or not number:
        raise InputError("Podaj obręb i numer działki.")
    try:
        rows = await _uldk_matches(region, number, commune)
    except ParcelLookupError:
        rows = await _indexed_matches(region, number, commune)
        if not rows:
            raise
    if not rows:
        place = f"obrębie {region}" + (f", gmina {commune}" if commune else "")
        raise ParcelLookupError(f"Nie ma działki nr {number} w {place}.")
    if len(rows) > 1:
        raise ParcelLookupError(
            "Działka o tym numerze jest w kilku obrębach o tej nazwie. Wybierz właściwą albo wpisz gminę.",
            _candidates(rows),
        )
    return await resolve_by_id(rows[0]["id"], with_land_use)


def _lat_lon(address: dict) -> tuple[float, float]:
    point = geom_to_4326(Point(address["x"], address["y"]))
    return point.y, point.x


async def _address_candidates(found: list[dict]) -> list[dict]:
    async def one(address: dict) -> dict | None:
        try:
            parcel, _ = await resolve_by_point(*_lat_lon(address), with_land_use=False)
        except (ParcelLookupError, InputError):
            return None
        return {
            "id": parcel.id,
            "commune": address.get("commune"),
            "region": parcel.region,
            "county": address.get("county"),
            "label": geocode.label(address),
        }

    results = await asyncio.gather(*[one(a) for a in found[:MAX_CANDIDATES]])
    return [c for c in results if c]


async def resolve_by_address(
    city: str, street: str, number: str, commune: str = ""
) -> tuple[Parcel, list[DataSource], str]:
    city, street, number, commune = (value.strip() for value in (city, street, number, commune))
    if not city or not number:
        raise InputError("Podaj miejscowość i numer domu.")
    try:
        found = await geocode.addresses(city, street, number)
    except geocode.AddressNotFound as exc:
        raise ParcelLookupError(f"Nie udało się sprawdzić adresu: {exc}") from exc
    found = [a for a in found if _same_place(a.get("commune"), commune)]
    if not found:
        where = f" w gminie {commune}" if commune else ""
        raise ParcelLookupError(f"Nie znaleziono tego adresu{where}. Sprawdź miejscowość, ulicę i numer domu.")
    if len(found) > 1:
        raise ParcelLookupError(
            "Taki adres jest w kilku miejscowościach. Wybierz właściwą albo wpisz gminę.",
            await _address_candidates(found),
        )
    parcel, sources = await resolve_by_point(*_lat_lon(found[0]))
    sources.insert(0, geocode.data_source())
    return parcel, sources, geocode.label(found[0])
