import hashlib
import hmac
import re
import secrets
from datetime import date
from functools import lru_cache
from typing import Literal

import anthropic
import httpx
from pydantic import BaseModel, Field

from app.assistant import links
from app.assistant.links import Link
from app.assistant.prompt import PERSONA
from app.core.schemas import Report
from app.land.settings import data_dir, land_settings
from app.report.summary import summarize

MAX_HISTORY = 12
_PROCESS_SECRET = secrets.token_bytes(32)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)
    signature: str | None = Field(default=None, max_length=64)


class AssistantRequest(BaseModel):
    report_id: str = Field(max_length=40)
    question: str = Field(min_length=1, max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)


class AssistantAnswer(BaseModel):
    answer: str
    mode: str
    evidence: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    signature: str | None = None


QUICK_QUESTIONS = {
    "dlaczego": "Dlaczego moje pole jest suche?",
    "najpierw": "Co zrobić najpierw?",
    "nawadniac": "Czy nawadniać w tym tygodniu?",
    "zatrzymac": "Gdzie mogę zatrzymać wodę?",
    "pewnosc": "Na ile mogę ufać temu raportowi?",
    "doplaty": "Czy dostanę na to dopłatę?",
}

OFFLINE = "bez AI"


@lru_cache(maxsize=1)
def evidence_text() -> str:
    return (data_dir() / "evidence.md").read_text(encoding="utf-8")


REPORT_EXCLUDE = {
    "parcel": {"geometry_wkt_2180", "geometry_geojson"},
    "terrain": {"depressions", "flow_lines", "details"},
    "hydro": {
        "details": True,
        "watercourses": {"__all__": {"geometry"}},
        "ditches": {"__all__": {"geometry"}},
        "water_bodies": {"__all__": {"geometry"}},
    },
    "satellite": {"details"},
    "water": {"meteo_last_90", "forecast"},
    "recommendations": {"__all__": {"location"}},
}


def _report_context(report: Report) -> str:
    summary = summarize(report).model_dump_json()
    body = report.model_dump_json(exclude=REPORT_EXCLUDE)
    return f"Ocena: {summary}\nRaport: {body}"


def _evidence_ids(text: str) -> list[str]:
    return sorted(set(re.findall(r"E\d{2}", text)))


def _has(q: str, *words: str) -> bool:
    return any(w in q for w in words)


def _num(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "brak danych"
    return f"{value:.{digits}f}".replace(".", ",")


def _offline(text: str, question: str, evidence: list[str] | None = None, extra: list[Link] | None = None):
    found = list({link.url: link for link in (extra or []) + links.for_question(question)}.values())[:3]
    if found:
        text += "\n\nSprawdź też:\n" + "\n".join(f"{link.title}: {link.url}" for link in found)
    return AssistantAnswer(
        answer=text, mode=OFFLINE, evidence=evidence if evidence is not None else _evidence_ids(text), links=found
    )


def _causes(report: Report, question: str) -> AssistantAnswer:
    headline = summarize(report).headline
    if not report.causes:
        return _offline(f"{headline} Raport nie wskazuje jednej wyraźnej przyczyny niedoboru wody.", question)
    text = f"{headline} Główne przyczyny:\n" + "\n".join(
        f"{i}. {c.label.capitalize()}. {c.evidence}" for i, c in enumerate(report.causes[:3], 1)
    )
    return _offline(text, question)


def _first_steps(report: Report, question: str) -> AssistantAnswer:
    recs = sorted(report.recommendations, key=lambda r: r.priority)[:3]
    if not recs:
        return _offline("Raport nie zawiera rekomendacji dla tej działki.", question)
    text = "Na początek:\n" + "\n".join(f"{i}. {r.title}. {r.justification}" for i, r in enumerate(recs, 1))
    return _offline(text, question, sorted({e for r in recs for e in r.evidence_ids}))


def _irrigation(report: Report, question: str) -> AssistantAnswer:
    irr = report.irrigation
    if not irr:
        return _offline("Raport nie zawiera oceny nawadniania.", question)
    text = f"{irr.status.capitalize()}. {irr.reason}"
    if irr.first_day and irr.net_dose_mm:
        text += f" Pierwsze podlewanie {irr.first_day.isoformat()}, dawka netto {_num(irr.net_dose_mm)} mm."
    text += f" {irr.legal_note}"
    return _offline(text, question, ["E01", "E11"], links.TOPICS["prawo_wodne"][1][:1])


def _soil_water(report: Report, question: str) -> AssistantAnswer:
    sw = report.water.soil_water if report.water else None
    if sw is None:
        return _offline("Raport nie ma bilansu wody w glebie na ten dzień, bo uprawa jest poza sezonem.", question)
    text = (
        f"Na {sw.date.isoformat()} w strefie korzeni ({_num(sw.root_depth_m, 1)} m) zostało {_num(sw.available_pct)}% "
        f"wody dostępnej dla roślin. W tym sezonie było {sw.stress_days_season} dni stresu wodnego."
    )
    if sw.percentile_10y is not None:
        text += f" Na tle 10 lat to {_num(sw.percentile_10y)}. percentyl dla tej daty."
    return _offline(text, question, ["E01"])


def _rain(report: Report, question: str) -> AssistantAnswer:
    if not report.water:
        return _offline("Raport nie ma danych meteorologicznych.", question)
    c = report.water.climate
    text = f"Przez ostatnie 30 dni spadło {_num(c.precip_30d_mm)} mm"
    text += f", a średnio w tym okresie pada {_num(c.precip_30d_norm_mm)} mm." if c.precip_30d_norm_mm else "."
    text += f" Klimatyczny bilans wodny z 60 dni (opad minus parowanie) wynosi {_num(c.kbw_60d_mm)} mm."
    if c.dry_spell_current_days:
        text += f" Bez deszczu jest od {c.dry_spell_current_days} dni."
    return _offline(text, question, ["E02"], links.TOPICS["pogoda"][1][:1])


def _soil(report: Report, question: str) -> AssistantAnswer:
    s = report.soil
    if not s:
        return _offline("Raport nie ma danych o glebie.", question)
    text = (
        f"W wierzchniej warstwie gleba to {s.texture_topsoil}, "
        f"materii organicznej {_num(s.organic_matter_pct_topsoil, 1)}%."
    )
    if s.iung_category:
        text += f" Kategoria agronomiczna IUNG: {s.iung_category} ({s.iung_category_source})."
    text += f" Pewność danych glebowych: {s.confidence}."
    return _offline(text, question)


def _satellite(report: Report, question: str) -> AssistantAnswer:
    sat = report.satellite
    if not sat or sat.ndvi is None:
        return _offline("Raport nie ma aktualnego zdjęcia satelitarnego tej działki.", question)
    scene = sat.last_scene_date.isoformat() if sat.last_scene_date else "nieznanego dnia"
    text = (
        f"Ostatnie zdjęcie satelitarne jest z {scene}."
        f" Wskaźnik zieleni roślin NDVI wynosi {_num(sat.ndvi, 2)}, stan powierzchni: {sat.surface_state}."
    )
    if sat.vci is not None:
        text += f" Na tle poprzednich lat (VCI) to {_num(sat.vci)} na 100."
    return _offline(text, question)


def _retention(report: Report, question: str) -> AssistantAnswer:
    retention = [r for r in report.recommendations if r.category == "retencja"][:3]
    if not retention:
        return _offline("Raport nie wskazał miejsc do zatrzymania wody na tej działce.", question)
    text = "\n".join(f"{r.title}. {r.justification}" for r in retention)
    return _offline(text, question, sorted({e for r in retention for e in r.evidence_ids}))


def _confidence(report: Report, question: str) -> AssistantAnswer:
    if not report.confidence:
        return _offline("Raport nie ocenia pewności swoich części.", question)
    text = "Pewność części raportu: " + ", ".join(f"{c.section} {c.level}" for c in report.confidence) + "."
    if report.limitations:
        text += " Najważniejsze ograniczenie: " + report.limitations[0].message
    return _offline(text, question)


def _permits(report: Report, question: str) -> AssistantAnswer:
    note = report.irrigation.legal_note if report.irrigation else ""
    text = note or "Raport nie ocenia spraw wodnoprawnych."
    text += " Ostateczną odpowiedź da nadzór wodny Wód Polskich właściwy dla Twojej gminy."
    return _offline(text, question, extra=links.TOPICS["prawo_wodne"][1])


def _subsidies(report: Report, question: str) -> AssistantAnswer:
    schemes = list(dict.fromkeys(r.eco_scheme for r in report.recommendations if r.eco_scheme))
    if not schemes:
        return _offline("Raport nie wiąże zaleceń z dopłatami. Warunki sprawdzisz w ARiMR albo w ODR.", question)
    text = "Możliwe wsparcie: " + "; ".join(schemes) + ". Warunki i stawki potwierdź w ARiMR albo w ODR."
    return _offline(text, question, ["E21"])


def _groundwater(report: Report, question: str) -> AssistantAnswer:
    gw = (report.hydro.groundwater if report.hydro else None) or {}
    body = gw.get("body") or {}
    if not body:
        return _offline("Raport nie ma danych o wodach podziemnych dla tego miejsca.", question)
    text = (
        f"Działka leży w jednolitej części wód podziemnych {body.get('code', '')}. "
        f"Stan ilościowy: {body.get('quantitative_status', 'brak oceny')}."
    )
    wells = [w for w in gw.get("wells", []) if "water_table_depth_m" in w]
    if wells:
        w = wells[0]
        text += (
            f" Najbliższy punkt pomiarowy ({w['distance_km']} km) pokazał zwierciadło wody"
            f" na głębokości {w['water_table_depth_m']} m."
        )
    return _offline(text, question)


ROUTES = [
    (("dlaczego", "przyczyn", "sucho", "suche"), _causes),
    (("najpierw", "zrobić", "zrobic", "co robić", "co robic", "od czego zacząć"), _first_steps),
    (("nawadn", "podlew", "deszczown"), _irrigation),
    (("zatrzym", "retenc", "oczk", "zastawk"), _retention),
    (("ufać", "ufac", "pewn", "dokładn", "dokladn", "wiarygod"), _confidence),
    (("dopłat", "doplat", "ekoschemat"), _subsidies),
    (("pozwoleni", "wodnopraw", "zgłoszeni", "zgloszeni"), _permits),
    (("podziemn", "zwierciad"), _groundwater),
    (("wilgot", "w glebie", "zapas wody", "ile wody"), _soil_water),
    (("opad", "deszcz", "bilans", "kbw"), _rain),
    (("satelit", "ndvi", "zdjęci", "zdjeci"), _satellite),
    (("gleb", "piach", "glin", "próchnic", "prochnic"), _soil),
]


def offline_answer(report: Report, question: str) -> AssistantAnswer:
    q = question.lower()
    for words, handler in ROUTES:
        if _has(q, *words):
            return handler(report, question)
    found = links.for_question(question)
    if found:
        return _offline("W raporcie działki tego nie ma, a bez modelu AI nie odpowiem szerzej.", question)
    text = (
        "Bez modelu AI odpowiadam tylko z raportu, a tu nie znalazłam odpowiedzi. "
        "Zapytaj na przykład o przyczyny suszy, wodę w glebie, opady, nawadnianie albo zatrzymanie wody."
    )
    return _offline(text, question, extra=links.DEFAULT[:2])


def _secret() -> bytes:
    configured = land_settings().assistant_secret
    return configured.encode() if configured else _PROCESS_SECRET


def sign(report_id: str, text: str) -> str:
    return hmac.new(_secret(), f"{report_id}\n{text}".encode(), hashlib.sha256).hexdigest()


def _trusted(report_id: str, turn: Turn) -> bool:
    if turn.role == "user":
        return True
    return turn.signature is not None and hmac.compare_digest(turn.signature, sign(report_id, turn.content))


def _messages(report_id: str, history: list[Turn], question: str) -> list[dict]:
    turns: list[Turn] = []
    for turn in history[-MAX_HISTORY:]:
        if not _trusted(report_id, turn):
            continue
        if not turns and turn.role != "user":
            continue
        if turns and turns[-1].role == turn.role:
            turns[-1] = turn
            continue
        turns.append(turn)
    if turns and turns[-1].role == "user":
        turns.pop()
    return [{"role": t.role, "content": t.content} for t in turns] + [{"role": "user", "content": question}]


@lru_cache(maxsize=1)
def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=land_settings().anthropic_api_key, timeout=60.0, max_retries=1)


_usage: dict = {"day": None, "count": 0, "reports": {}}


def _over_limit(report_id: str) -> str | None:
    today = date.today()
    if _usage["day"] != today:
        _usage.update(day=today, count=0, reports={})
    settings = land_settings()
    if _usage["count"] >= settings.assistant_daily_limit:
        return "dzienny limit"
    used = _usage["reports"].get(report_id, 0)
    if used >= settings.assistant_report_limit:
        return "limit pytań do raportu"
    _usage["count"] += 1
    _usage["reports"][report_id] = used + 1
    return None


FACT_HANDLERS = (
    _causes,
    _first_steps,
    _irrigation,
    _soil_water,
    _rain,
    _soil,
    _satellite,
    _retention,
    _confidence,
    _subsidies,
    _groundwater,
)
OLLAMA_TURNS = 4
REFUSAL = "Na to nie odpowiem. Chętnie pogadam o wodzie i uprawach na Twojej działce."


def _model_ready() -> bool:
    settings = land_settings()
    if settings.assistant_provider == "ollama":
        return bool(settings.ollama_url and settings.ollama_model)
    return bool(settings.anthropic_api_key)


def _unavailable(report: Report, question: str) -> AssistantAnswer:
    fallback = offline_answer(report, question)
    fallback.mode = "bez AI (model niedostępny)"
    return fallback


def _facts(report: Report) -> str:
    texts = (handler(report, "").answer.split("\n\nSprawdź też:")[0] for handler in FACT_HANDLERS)
    return "\n".join(texts)


def _strip_reasoning(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def _ask_ollama(report: Report, history: list[Turn], question: str) -> str | None:
    settings = land_settings()
    system = (
        f"{PERSONA}\n\nRejestr źródeł:\n{evidence_text()}\n\n"
        f"Fakty z raportu działki:\n{_facts(report)}\n\nOcena (JSON): {summarize(report).model_dump_json()}"
    )
    messages = _messages(report.id, history, question)[-(2 * OLLAMA_TURNS + 1) :]
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [{"role": "system", "content": system}, *messages],
        "options": {
            "num_ctx": settings.ollama_num_ctx,
            "num_predict": settings.ollama_num_predict,
            "temperature": 0.2,
        },
    }
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
        response = await client.post(settings.ollama_url.rstrip("/") + "/api/chat", json=payload)
        response.raise_for_status()
    return _strip_reasoning(response.json().get("message", {}).get("content", ""))


async def _ask_anthropic(report: Report, history: list[Turn], question: str) -> str | None:
    settings = land_settings()
    system = [
        {"type": "text", "text": PERSONA},
        {"type": "text", "text": "Rejestr źródeł:\n" + evidence_text(), "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": "Raport działki (JSON):\n" + _report_context(report),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    response = await _client().beta.messages.create(
        model=settings.assistant_model,
        max_tokens=settings.assistant_max_tokens,
        system=system,
        output_config={"effort": settings.assistant_effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=_messages(report.id, history, question),
    )
    if response.stop_reason == "refusal":
        return None
    return "".join(block.text for block in response.content if block.type == "text").strip()


async def answer(report: Report, question: str, history: list[Turn] | None = None) -> AssistantAnswer:
    if report.mock or not _model_ready():
        return offline_answer(report, question)
    limit = _over_limit(report.id)
    if limit:
        fallback = offline_answer(report, question)
        fallback.mode = f"bez AI ({limit})"
        return fallback
    ask = _ask_ollama if land_settings().assistant_provider == "ollama" else _ask_anthropic
    try:
        text = await ask(report, history or [], question)
    except (anthropic.APIError, httpx.HTTPError, ValueError):
        return _unavailable(report, question)
    if text is None:
        return AssistantAnswer(answer=REFUSAL, mode="AI")
    if not text:
        return _unavailable(report, question)
    return AssistantAnswer(answer=text, mode="AI", evidence=_evidence_ids(text), links=links.in_text(text))
