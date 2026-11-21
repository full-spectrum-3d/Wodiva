import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api import analyze, health, parcel
from app.core.config import get_settings
from app.core.http import close_client
from app.core.security import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_client()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Wodiva API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    for router in (health.router, parcel.router, analyze.router):
        app.include_router(router, prefix="/api")
    for module in ("app.report.api", "app.assistant.api"):
        try:
            app.include_router(importlib.import_module(module).router, prefix="/api")
        except ModuleNotFoundError:
            pass
    return app


app = create_app()
