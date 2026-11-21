import asyncio
import math
from datetime import UTC, date, datetime

from shapely.geometry.base import BaseGeometry

from app.land.cache import DAY, cache
from app.land.net import client
from app.land.settings import land_settings

BASE = "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/hydrogeologia/"
WELL_RADIUS_M = 15_000
WELLS_LIMIT = 3
JCWPD_LAYERS = (5, 2)
GZWP_LAYERS = (0, 1)


async def _query(service: str, layer: int, params: dict) -> list[dict]:
    key = cache.make_key("pigpib", service, layer, params)
    cached = cache.get(key)
    if cached is not None:
        return cached
    query = {"f": "json", "inSR": "2180", "outSR": "2180", "spatialRel": "esriSpatialRelIntersects", **params}
    response = await client().get(
        f"{BASE}{service}/MapServer/{layer}/query", params=query, timeout=land_settings().source_timeout_s
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise ValueError(str(payload["error"]))
    features = payload.get("features", [])
    cache.set(key, features, 30 * DAY)
    return features


def _point(x: float, y: float) -> dict:
    return {"geometry": f"{x},{y}", "geometryType": "esriGeometryPoint", "outFields": "*", "returnGeometry": "false"}


def _well(feature: dict, x: float, y: float, day: date) -> dict:
    a = feature["attributes"]
    g = feature.get("geometry") or {}
    distance = math.hypot(g.get("x", x) - x, g.get("y", y) - y)
    measured = datetime.fromtimestamp(a["DATA_POMIARU"] / 1000, UTC).date() if a.get("DATA_POMIARU") else None
    item = {
        "id": a.get("NR_PKT_MONIT_ILOSC") or a.get("NUMER_CBDH"),
        "place": a.get("MIEJSCOWOSC"),
        "distance_km": round(distance / 1000, 1),
        "observed_now": a.get("AKTUALNIE_OBSERWOWANY") == "Tak",
        "aquifer": a.get("CHARAKTER_PUNKTU"),
        "stratigraphy": a.get("CHRONO"),
        "lithology": a.get("LITOLOGIA"),
        "ground_level_m": a.get("RZEDNA_TERENU"),
    }
    if measured is not None and a.get("GLEBOKOSC_ZWIERCIADLA") is not None:
        if measured <= day:
            item["water_table_depth_m"] = a["GLEBOKOSC_ZWIERCIADLA"]
            item["measured_on"] = measured.isoformat()
        else:
            item["measurement_after_analysis_date"] = measured.isoformat()
    return {k: v for k, v in item.items() if v not in (None, "", " ")}


async def _wells(x: float, y: float, day: date) -> list[dict]:
    envelope = {
        "geometry": f"{x - WELL_RADIUS_M},{y - WELL_RADIUS_M},{x + WELL_RADIUS_M},{y + WELL_RADIUS_M}",
        "geometryType": "esriGeometryEnvelope",
        "outFields": "*",
        "returnGeometry": "true",
    }
    features = await _query("mwp", 0, envelope)
    wells = [_well(f, x, y, day) for f in features]
    wells.sort(key=lambda w: (not w.get("observed_now", False), w["distance_km"]))
    return wells[:WELLS_LIMIT]


async def _body(x: float, y: float) -> dict | None:
    for layer in JCWPD_LAYERS:
        features = await _query("jcwpd", layer, _point(x, y))
        if features:
            a = features[0]["attributes"]
            body = {
                "code": a.get("KOD_UE"),
                "number": a.get("NR_JCWPD"),
                "river_basin": a.get("DORZECZE"),
                "water_region": a.get("REGION_WODNY"),
                "quantitative_status": a.get("STAN_ILOSCIOWY_2022"),
                "chemical_status": a.get("STAN_CHEMICZNY_2022"),
                "overall_status": a.get("STAN_OGOLNY_2022"),
                "risk": a.get("RYZYKO_2025"),
                "status_year": 2022 if a.get("STAN_ILOSCIOWY_2022") else None,
            }
            return {k: v for k, v in body.items() if v not in (None, "")}
    return None


async def _aquifer(x: float, y: float) -> dict | None:
    for layer in GZWP_LAYERS:
        features = await _query("gzwp", layer, _point(x, y))
        if features:
            a = features[0]["attributes"]
            item = {
                "name": a.get("NAZWA"),
                "number": a.get("NR_GZWP"),
                "rank": a.get("RANGA_ZWP"),
                "documented": a.get("STAN_UDOKUMENTOWANIA"),
                "depth_mean_m": a.get("GL_SR_M"),
            }
            return {k: v for k, v in item.items() if v not in (None, "", 0)}
    return None


async def groundwater(geom_2180: BaseGeometry, day: date) -> dict:
    x, y = geom_2180.centroid.x, geom_2180.centroid.y
    wells, body, aquifer = await asyncio.gather(_wells(x, y, day), _body(x, y), _aquifer(x, y))
    return {
        "wells": wells,
        "body": body,
        "major_aquifer": aquifer,
        "source": "PIG-PIB, Państwowa Służba Hydrogeologiczna",
    }


def is_quantity_poor(groundwater_info: dict | None) -> bool:
    body = (groundwater_info or {}).get("body") or {}
    return body.get("quantitative_status") == "słaby" or body.get("risk") == "zagrożona"
