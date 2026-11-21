from fastapi import APIRouter, HTTPException, Query

from app.core.schemas import DataSource, Parcel
from app.core.validation import InputError
from app.water.engine.crops import load_crops
from app.water.parcel import ParcelLookupError, resolve_by_id, resolve_by_point

router = APIRouter()


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
