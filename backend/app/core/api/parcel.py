import re

from fastapi import APIRouter, HTTPException, Query

from app.core.schemas import DataSource, Parcel
from app.core.validation import InputError
from app.water.engine.crops import load_crops
from app.water.parcel import ParcelLookupError, resolve_by_id, resolve_by_point
from app.water.sources import parcels_parquet

router = APIRouter()
SEARCH_TEXT = re.compile(r"[\w .,/-]*")


@router.get("/parcel")
async def parcel(
    id: str | None = Query(None, max_length=80),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
) -> dict:
    try:
        if id:
            found, sources = await resolve_by_id(id)
        elif lat is not None and lon is not None:
            found, sources = await resolve_by_point(lat, lon)
        else:
            raise InputError("Podaj identyfikator działki (id) albo współrzędne (lat, lon).")
    except InputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ParcelLookupError as exc:
        raise HTTPException(404, {"message": str(exc), "candidates": exc.candidates}) from exc
    return {
        "parcel": Parcel.model_validate(found),
        "sources": [DataSource.model_validate(s) for s in sources],
    }


@router.get("/parcels/search")
async def parcels_search(
    gmina: str = Query(..., min_length=3, max_length=60),
    obreb: str = Query("", max_length=60),
    numer: str = Query("", max_length=20),
    limit: int = Query(20, ge=1, le=20),
) -> list[dict]:
    values = [value.strip() for value in (gmina, obreb, numer)]
    if not all(SEARCH_TEXT.fullmatch(value) for value in values) or len(values[0]) < 3:
        raise HTTPException(422, "Wpisz co najmniej 3 litery nazwy gminy, bez znaków specjalnych.")
    try:
        return await parcels_parquet.search(*values, limit)
    except LookupError as exc:
        raise HTTPException(503, "Wyszukiwarka działek jest niedostępna: brak lokalnego indeksu.") from exc


@router.get("/crops")
async def crops() -> list[dict]:
    return [
        {
            "code": c.code,
            "name": c.name,
            "critical_period": f"{c.critical_start} – {c.critical_end}",
            "critical_label": c.critical_label,
            "has_kbw_threshold": c.kbw_group is not None,
        }
        for c in load_crops().values()
    ]
