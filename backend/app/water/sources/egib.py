import asyncio
import html
import re
from collections import Counter
from datetime import UTC, datetime

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from app.core.cache import get_cache
from app.core.http import SourceError, fetch
from app.core.schemas import DataSource, LandUseShare, SourceStatus

URL = "https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow"
AGRICULTURAL = {"R", "Ł", "Ps", "S", "Br", "Wsr", "W", "Lz"}
UNAVAILABLE = "usługa niedostępna"
OFU = (
    "R|Ł|Ps|S-R|S-Ł|S-Ps|S|Br-R|Br-Ł|Br-Ps|Br|Wsr-R|Wsr-Ł|Wsr-Ps|Wsr|W-R|W-Ł|W-Ps|W|Lz-R|Lz-Ł|Lz-Ps|Lz|"
    "Ls|N|B|Ba|Bi|Bp|Bz|K|dr|Tk|Ti|Tp|Wm|Wp|Ws|Tr"
)
CLASS = r"I|II|IIIa|IIIb|III|IVa|IVb|IV|V|VI|VIz"
CELL_RE = re.compile(rf"^(?P<ofu>{OFU})\s?-?\s?(?P<cls>{CLASS})?$")
TD_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def data_source(status: SourceStatus = SourceStatus.ok, note: str | None = None) -> DataSource:
    return DataSource(
        name="EGiB – Krajowa Integracja Ewidencji Gruntów (WMS KIEG, warstwy użytki/kontury)",
        url=URL,
        license="Dane publiczne GUGiK i starostw, bezpłatne",
        retrieved_at=datetime.now(UTC),
        status=status,
        note=note,
    )


def parse_feature_info(text: str) -> list[tuple[str, str | None]]:
    found = []
    cells = TD_RE.findall(text) or text.splitlines()
    for cell in cells:
        value = html.unescape(TAG_RE.sub("", cell)).strip()
        m = CELL_RE.match(value)
        if m:
            found.append((m.group("ofu").split("-")[0], m.group("cls")))
    return found


def sample_points(geom: BaseGeometry, n: int = 5) -> list[Point]:
    points = [geom.representative_point()]
    minx, miny, maxx, maxy = geom.bounds
    inner = geom.buffer(-min(5.0, (maxx - minx) / 10))
    target = inner if not inner.is_empty else geom
    steps = 7
    for i in range(1, steps):
        for j in range(1, steps):
            p = Point(minx + (maxx - minx) * i / steps, miny + (maxy - miny) * j / steps)
            if target.contains(p):
                points.append(p)
    if len(points) <= n:
        return points
    stride = max(1, (len(points) - 1) // (n - 1))
    return [points[0], *points[1::stride][: n - 1]]


async def _point_info(x: float, y: float) -> list[tuple[str, str | None]]:
    async def run():
        d = 2.0
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": "uzytki,kontury",
            "QUERY_LAYERS": "uzytki,kontury",
            "STYLES": ",",
            "CRS": "EPSG:2180",
            "BBOX": f"{y - d},{x - d},{y + d},{x + d}",
            "WIDTH": "5",
            "HEIGHT": "5",
            "I": "2",
            "J": "2",
            "INFO_FORMAT": "text/html",
            "FORMAT": "image/png",
        }
        response = await fetch("egib", URL, params=params, retries=0)
        # None, nie []: pusta odpowiedź WMS (np. strona błędu z HTTP 200) nie może trafić do cache na 30 dni
        return [list(item) for item in parse_feature_info(response.text)] or None

    rows = await get_cache().get_or_fetch("egib", (round(x, 1), round(y, 1)), run)
    return [tuple(r) for r in rows or []]


async def land_use(geom_2180: BaseGeometry) -> tuple[list[LandUseShare], DataSource]:
    points = sample_points(geom_2180)
    results = await asyncio.gather(*[_point_info(p.x, p.y) for p in points], return_exceptions=True)
    ok = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, SourceError)]
    hits = [r[0] for r in ok if r]
    if not hits:
        note = UNAVAILABLE if errors else "brak informacji o użytkach w odpowiedzi WMS"
        return [], data_source(SourceStatus.missing, note)
    counts = Counter(hits)
    total = sum(counts.values())
    shares = [
        LandUseShare(code=code, soil_class=cls, share=round(n / total, 2)) for (code, cls), n in counts.most_common()
    ]
    status = SourceStatus.ok if len(hits) == len(points) else SourceStatus.partial
    return shares, data_source(status, f"próbkowanie {len(points)} punktów w działce, trafienia: {len(hits)}")


def is_agricultural(shares: list[LandUseShare]) -> bool | None:
    if not shares:
        return None
    agri = sum(s.share or 0 for s in shares if s.code in AGRICULTURAL)
    return agri >= 0.5


INDEX_DATA_URL = "https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/PARQUET/"


def shares_from_codes(codes: str | None) -> list[LandUseShare]:
    found = []
    for token in (codes or "").split(","):
        match = CELL_RE.match(token.strip().replace("/", "-"))
        if match:
            found.append((match["ofu"].split("-")[0], match["cls"]))
    shares = []
    for (code, cls), n in Counter(found).most_common():
        shares.append(LandUseShare(code=code, soil_class=cls, share=round(n / len(found), 2)))
    return shares


def index_source(codes: str) -> DataSource:
    return DataSource(
        name="EGiB – klasoużytki z lokalnego indeksu działek",
        url=INDEX_DATA_URL,
        license="Dane publiczne GUGiK, bezpłatne",
        retrieved_at=datetime.now(UTC),
        status=SourceStatus.ok,
        note=f"klasoużytki: {codes}; udziały przybliżone, bo eksport podaje listę klasoużytków bez powierzchni",
    )
