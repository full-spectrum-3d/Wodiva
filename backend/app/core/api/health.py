from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import get_settings
from app.water.sources import era5

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    ds = era5.open_cube()
    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "era5_cube": {
            "available": ds is not None,
            "until": era5.cube_end(ds).isoformat() if ds is not None else None,
            "path": str(get_settings().era5_cube_path),
        },
    }
