import httpx

from app.core.http import get_client


def client() -> httpx.AsyncClient:
    return get_client()
