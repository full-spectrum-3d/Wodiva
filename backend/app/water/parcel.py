import logging

from shapely.geometry.base import BaseGeometry

from app.core.schemas import DataSource, Parcel, SourceStatus
from app.core.validation import is_full_parcel_id, normalize_parcel_id, validate_lat_lon
from app.water.geo import count_parts, geojson_4326, geom_to_4326, parse_wkt, reproject, to_2180
from app.water.sources import egib, parcels_parquet, uldk

log = logging.getLogger("wodiva.parcel")

SMALL_HA = 1.0
LARGE_HA = 50.0


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


async def _with_land_use(parcel: Parcel, sources: list[DataSource]) -> Parcel:
    shares, ds = await egib.land_use(parse_wkt(parcel.geometry_wkt_2180))
    sources.append(ds)
    parcel.land_use = shares
    parcel.is_agricultural = egib.is_agricultural(shares)
    if parcel.is_agricultural is False:
        parcel.flags.append("działka nierolnicza wg EGiB")
    return parcel


def _candidates(rows: list[dict]) -> list[dict]:
    return [
        {"id": r["id"], "commune": r.get("commune"), "region": r.get("region"), "county": r.get("county")}
        for r in rows[:20]
    ]


async def resolve_by_id(raw_id: str, with_land_use: bool = True) -> tuple[Parcel, list[DataSource]]:
    parcel_id = normalize_parcel_id(raw_id)
    sources: list[DataSource] = []
    try:
        rows = await uldk.by_id(parcel_id)
        if len(rows) > 1 and not is_full_parcel_id(parcel_id):
            raise ParcelLookupError("Znaleziono kilka działek – wybierz właściwą.", _candidates(rows))
        parcel = build_parcel(rows[0], "ULDK")
        sources.append(uldk.data_source())
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
        parcel = build_parcel(row, "EGiB parquet")
        sources.append(parcels_parquet.data_source(parcel_id=parcel_id))
    if with_land_use:
        parcel = await _with_land_use(parcel, sources)
    return parcel, sources


async def resolve_by_point(lat: float, lon: float, with_land_use: bool = True) -> tuple[Parcel, list[DataSource]]:
    validate_lat_lon(lat, lon)
    sources: list[DataSource] = []
    try:
        rows = await uldk.by_xy(lat, lon)
    except uldk.ParcelNotFound as exc:
        raise ParcelLookupError(f"Nie znaleziono działki w tym miejscu: {exc}") from exc
    parcel = build_parcel(rows[0], "ULDK")
    sources.append(uldk.data_source())
    if with_land_use:
        parcel = await _with_land_use(parcel, sources)
    return parcel, sources
