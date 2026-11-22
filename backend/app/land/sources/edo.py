from __future__ import annotations

import io
import re
from datetime import date, timedelta

import httpx
import matplotlib.image as mpimg
import numpy as np

from app.land.cache import DAY, cache
from app.land.models import DataStatus, DroughtContext
from app.land.net import client
from app.land.settings import land_settings

WMS_URL = "https://drought.emergency.copernicus.eu/api/wms"
LAYER = "cdiad"
FIRST_DATE = date(2012, 1, 1)
CAPABILITIES_LATEST = re.compile(r"<Name>cdiad</Name>.*?/(\d{4}-\d{2}-\d{2})/P10D", re.DOTALL)
CLASSES = {
    (220, 5, 12): ("alarm", "deficyt opadu, niedobór wilgotności gleby i osłabiona roślinność (fAPAR)"),
    (230, 159, 0): ("ostrzeżenie", "deficyt opadu i niedobór wilgotności gleby"),
    (240, 228, 66): ("obserwacja", "deficyt opadu"),
    (255, 255, 254): ("brak suszy", "brak sygnału suszy w składnikach wskaźnika"),
    (255, 255, 255): ("brak suszy", "brak sygnału suszy w składnikach wskaźnika"),
}


def dekad_start(day: date) -> date:
    return day.replace(day=1 if day.day < 11 else 11 if day.day < 21 else 21)


def last_complete_dekad(day: date) -> date:
    # CDI dekady liczony jest z danych do jej końca: bieżąca dekada wolna tylko w jej ostatnim dniu
    start = dekad_start(day)
    if dekad_start(day + timedelta(days=1)) != start:
        return start
    return dekad_start(start - timedelta(days=1))


def classify(rgb: tuple[int, int, int]) -> tuple[str, str]:
    best = min(CLASSES, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, rgb, strict=True)))
    if sum((a - b) ** 2 for a, b in zip(best, rgb, strict=True)) > 1200:
        return "inna klasa", "klasa przejściowa (np. odbudowa po suszy); szczegóły na mapie EDO"
    return CLASSES[best]


async def latest_published() -> date | None:
    key = cache.make_key("edo_latest", LAYER)
    stamp = cache.get(key)
    if stamp is None:
        try:
            response = await client().get(
                WMS_URL,
                params={"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetCapabilities"},
                timeout=land_settings().source_timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        match = CAPABILITIES_LATEST.search(response.text)
        if match is None:
            return None
        stamp = match[1]
        cache.set(key, stamp, DAY / 2)
    return date.fromisoformat(stamp)


async def cdi(lon: float, lat: float, day: date) -> DroughtContext:
    when = last_complete_dekad(day)
    published = await latest_published()
    if published is not None and when > published:
        when = published
    if when < FIRST_DATE:
        return DroughtContext(status=DataStatus.missing)
    key = cache.make_key("edo", round(lon, 2), round(lat, 2), str(when))
    cached = cache.get(key)
    if cached is None:
        size, half = 11, 0.25
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": LAYER,
            "STYLES": "",
            "SRS": "EPSG:4326",
            "BBOX": f"{lon - half},{lat - half},{lon + half},{lat + half}",
            "WIDTH": size,
            "HEIGHT": size,
            "FORMAT": "image/png",
            "TRANSPARENT": "TRUE",
            "TIME": when.isoformat(),
        }
        response = await client().get(WMS_URL, params=params, timeout=land_settings().source_timeout_s)
        response.raise_for_status()
        if not response.headers.get("content-type", "").startswith("image/png"):
            return DroughtContext(date=when, status=DataStatus.missing)
        cached = response.content
        cache.set(key, cached, 365 * DAY if when < date.today() - timedelta(days=30) else DAY / 2)
    image = mpimg.imread(io.BytesIO(cached), format="png")
    center = image[4:7, 4:7].reshape(-1, image.shape[-1])
    opaque = center[center[:, 3] > 0.5] if image.shape[-1] == 4 else center
    if len(opaque) == 0:
        return DroughtContext(
            date=when,
            cdi_class="brak klasy",
            cdi_meaning="mapa EDO nie pokazuje klasy suszy w tym miejscu (brak sygnału suszy albo brak danych)",
            status=DataStatus.partial,
        )
    rgb = tuple(int(v) for v in np.median(opaque[:, :3] * 255, axis=0).round())
    label, meaning = classify(rgb)
    return DroughtContext(date=when, cdi_class=label, cdi_meaning=meaning)
