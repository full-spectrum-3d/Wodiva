import asyncio
import contextlib
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api import analyze, health, parcel
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.http import close_client
from app.core.security import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


log = logging.getLogger("wodiva.main")
HOUSEKEEPING_EVERY_S = 24 * 3600


def purge_storage() -> None:
    """Usuwa wygasłe wpisy cache i stare raporty, żeby wolumen var/ nie rósł bez końca."""
    jobs = [("cache", lambda: get_cache().purge_expired())]
    land_cache = _optional_module("app.land.cache")
    if land_cache is not None:
        jobs.append(("land_cache", lambda: land_cache.get_cache().purge_expired()))
    store = _optional_module("app.report.store")
    if store is not None:
        jobs.append(("reports", lambda: store.purge(get_settings().report_retention_days)))
    for name, job in jobs:
        try:
            log.info("purge %s: %d rows", name, job())
        except Exception:
            log.exception("purge %s failed", name)


def _optional_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and name.startswith(exc.name):
            return None
        raise


async def _warm_assistant() -> None:
    kolba = _optional_module("app.assistant.kolba")
    if kolba is None:
        return
    try:
        await kolba.warm_up()
    except Exception:
        log.exception("assistant warm-up failed")


async def _housekeeping() -> None:
    while True:
        try:
            await asyncio.to_thread(purge_storage)
        except Exception:
            log.exception("housekeeping failed")
        await asyncio.sleep(HOUSEKEEPING_EVERY_S)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_housekeeping())
    warm = asyncio.create_task(_warm_assistant())
    yield
    for job in (task, warm):
        job.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await job
    await close_client()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Wodiva API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RateLimitMiddleware)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )
    for router in (health.router, parcel.router, analyze.router):
        app.include_router(router, prefix="/api")
    for module in ("app.report.api", "app.assistant.api"):
        found = _optional_module(module)
        if found is None:
            log.warning("pominięto router %s: moduł nie istnieje", module)
            continue
        app.include_router(found.router, prefix="/api")
    return app


app = create_app()
