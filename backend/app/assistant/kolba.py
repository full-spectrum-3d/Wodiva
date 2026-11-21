import re
from functools import lru_cache

import anthropic
from pydantic import BaseModel, Field

from app.core.schemas import Report
from app.land.settings import data_dir, land_settings
from app.report.summary import summarize

SYSTEM_PROMPT = """Jesteś Kolbą – przyjazną, gadającą kolbą kukurydzy w aplikacji Wodiva.
Pomagasz rolnikowi zrozumieć raport o wodzie na jego działce.

Zasady:
- Odpowiadasz po polsku, prosto, krótko (najwyżej 6 zdań), bez żargonu GIS i teledetekcji.
- Korzystasz wyłącznie z raportu działki i rejestru źródeł podanych niżej. Nie dopowiadasz faktów spoza nich.
- Każdą liczbę bierzesz dosłownie z raportu. Nie licz nowych wartości i nie zgaduj.
- Jeśli raportu brakuje danych do odpowiedzi, powiedz wprost, że tego nie wiesz,
  i wskaż, co rolnik może sprawdzić na polu albo u doradcy ODR.
- Gdy powołujesz się na wiedzę naukową, podaj identyfikator źródła w nawiasie, np. (E05).
- Przypominaj o ograniczeniach raportu, gdy pytanie ich dotyczy. Nie obiecuj plonów ani wyników finansowych.
- Sprawy prawne (pozwolenia wodnoprawne, dopłaty) kieruj do właściwego urzędu, spółki wodnej, ARiMR lub ODR."""


class AssistantRequest(BaseModel):
    report_id: str = Field(max_length=40)
    question: str = Field(min_length=1, max_length=500)


class AssistantAnswer(BaseModel):
    answer: str
    mode: str
    evidence: list[str] = Field(default_factory=list)


QUICK_QUESTIONS = {
    "dlaczego": "Dlaczego moje pole jest suche?",
    "najpierw": "Co zrobić najpierw?",
    "nawadniac": "Czy nawadniać w tym tygodniu?",
    "zatrzymac": "Gdzie mogę zatrzymać wodę?",
    "pewnosc": "Na ile mogę ufać temu raportowi?",
    "doplaty": "Czy dostanę na to dopłatę?",
}


@lru_cache(maxsize=1)
def evidence_text() -> str:
    return (data_dir() / "evidence.md").read_text(encoding="utf-8")


REPORT_EXCLUDE = {
    "parcel": {"geometry_wkt_2180", "geometry_geojson"},
    "terrain": {"depressions", "flow_lines", "details"},
    "hydro": {"details"},
    "satellite": {"details"},
    "water": {"meteo_last_90", "forecast"},
}


def _report_context(report: Report) -> str:
    summary = summarize(report).model_dump_json()
    body = report.model_dump_json(exclude=REPORT_EXCLUDE)
    return f"Ocena: {summary}\nRaport: {body}"


def _evidence_ids(text: str) -> list[str]:
    return sorted(set(re.findall(r"E\d{2}", text)))


def offline_answer(report: Report, question: str) -> AssistantAnswer:
    q = question.lower()
    summary = summarize(report)
    retention = [r for r in report.recommendations if r.category == "retencja"]
    if any(w in q for w in ("dlaczego", "przyczyn", "sucho", "suche")):
        if not report.causes:
            return AssistantAnswer(
                answer=f"{summary.headline} Raport nie wskazuje wyraźnej przyczyny niedoboru wody.", mode="bez AI"
            )
        text = f"{summary.headline} Główne przyczyny: " + "; ".join(
            f"{c.label.lower()} – {c.evidence}" for c in report.causes[:3]
        )
        return AssistantAnswer(answer=text, mode="bez AI", evidence=_evidence_ids(text))
    if any(w in q for w in ("najpierw", "zrobić", "zrobic", "co robić", "co robic")):
        recs = sorted(report.recommendations, key=lambda r: r.priority)[:3]
        if not recs:
            return AssistantAnswer(answer="Raport nie zawiera rekomendacji dla tej działki.", mode="bez AI")
        return AssistantAnswer(
            answer="Na początek: " + " ".join(f"{i}. {r.title}: {r.justification}" for i, r in enumerate(recs, 1)),
            mode="bez AI",
            evidence=sorted({e for r in recs for e in r.evidence_ids}),
        )
    if any(w in q for w in ("nawadn", "podlew")):
        irr = report.irrigation
        text = (
            f"{irr.status.capitalize()}: {irr.reason} {irr.legal_note}"
            if irr
            else "Raport nie zawiera oceny nawadniania."
        )
        return AssistantAnswer(answer=text, mode="bez AI", evidence=["E01", "E11"])
    if any(w in q for w in ("zatrzym", "retenc", "oczko", "rów", "row")):
        if not retention:
            return AssistantAnswer(
                answer="Raport nie wskazał miejsc do zatrzymania wody na tej działce.", mode="bez AI"
            )
        return AssistantAnswer(
            answer=" ".join(f"{r.title}: {r.justification}" for r in retention[:3]),
            mode="bez AI",
            evidence=sorted({e for r in retention[:3] for e in r.evidence_ids}),
        )
    if any(w in q for w in ("ufać", "ufac", "pewn", "dokładn", "dokladn")):
        text = "; ".join(f"{c.section}: pewność {c.level}" for c in report.confidence)
        if report.limitations:
            text += ". " + report.limitations[0].message
        return AssistantAnswer(answer=text, mode="bez AI")
    if any(w in q for w in ("dopłat", "doplat", "ekoschemat", "arimr")):
        schemes = list(dict.fromkeys(r.eco_scheme for r in report.recommendations if r.eco_scheme))
        if not schemes:
            return AssistantAnswer(
                answer="Raport nie wiąże zaleceń z dopłatami. Zapytaj w ARiMR lub ODR.", mode="bez AI"
            )
        return AssistantAnswer(
            answer="Możliwe wsparcie: " + "; ".join(schemes) + ". Warunki potwierdź w ARiMR lub ODR.",
            mode="bez AI",
            evidence=["E21"],
        )
    return AssistantAnswer(
        answer="Bez połączenia z modelem AI odpowiadam tylko na gotowe pytania: " + "; ".join(QUICK_QUESTIONS.values()),
        mode="bez AI",
    )


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=land_settings().anthropic_api_key, timeout=30.0, max_retries=1)


async def answer(report: Report, question: str) -> AssistantAnswer:
    if not land_settings().anthropic_api_key:
        return offline_answer(report, question)
    system = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": "Rejestr źródeł:\n" + evidence_text(), "cache_control": {"type": "ephemeral"}},
    ]
    try:
        response = await _client().beta.messages.create(
            model=land_settings().assistant_model,
            max_tokens=1200,
            system=system,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": f"Raport działki (JSON):\n{_report_context(report)}\n\nPytanie rolnika: {question}",
                }
            ],
        )
    except anthropic.APIError:
        fallback = offline_answer(report, question)
        fallback.mode = "bez AI (model niedostępny)"
        return fallback
    if response.stop_reason == "refusal":
        return AssistantAnswer(
            answer="Nie mogę odpowiedzieć na to pytanie. Zapytaj o wodę na swojej działce.", mode="AI"
        )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return AssistantAnswer(answer=text, mode="AI", evidence=_evidence_ids(text))
