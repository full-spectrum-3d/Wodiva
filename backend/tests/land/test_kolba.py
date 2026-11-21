import json
from types import SimpleNamespace

import anthropic
import httpx
import httpx2
import pytest

from app.assistant import kolba, links
from app.assistant.prompt import PERSONA
from app.land.settings import land_settings

from .test_service import _report


@pytest.fixture
def report(parcel, water, soil, irrigation, land):
    return _report(parcel, water, soil, irrigation, land)


@pytest.fixture
def fake_model(monkeypatch):
    calls = []
    reply = {"text": "Gleba ma mało wody (E01). Zajrzyj na https://susza.iung.pulawy.pl/", "stop": "end_turn"}

    async def create(**kwargs):
        calls.append(kwargs)
        if reply.get("error"):
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
        content = [SimpleNamespace(type="thinking", thinking="..."), SimpleNamespace(type="text", text=reply["text"])]
        return SimpleNamespace(stop_reason=reply["stop"], content=content)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(kolba, "_client", lambda: client)
    monkeypatch.setattr(land_settings(), "anthropic_api_key", "test-key")
    return SimpleNamespace(calls=calls, reply=reply)


async def test_ai_answer_uses_history_report_and_links(report, fake_model):
    history = [
        kolba.Turn(role="assistant", content="Cześć"),
        kolba.Turn(role="user", content="Co z wodą?"),
        kolba.Turn(role="assistant", content="Mało jej."),
        kolba.Turn(role="user", content="Pytanie bez odpowiedzi"),
    ]
    result = await kolba.answer(report, "A co z oziminą na zimę?", history)
    call = fake_model.calls[0]
    assert [m["role"] for m in call["messages"]] == ["user", "assistant", "user"]
    assert call["messages"][-1]["content"] == "A co z oziminą na zimę?"
    assert call["output_config"] == {"effort": "medium"} and "thinking" not in call
    assert report.id in call["system"][2]["text"] and call["system"][0]["text"] == PERSONA
    assert result.mode == "AI" and result.evidence == ["E01"]
    assert [link.url for link in result.links] == ["https://susza.iung.pulawy.pl/"]
    assert "thinking" not in result.answer and "..." not in result.answer


async def test_ai_errors_fall_back_to_report(report, fake_model):
    fake_model.reply["error"] = True
    result = await kolba.answer(report, "Co zrobić najpierw?")
    assert result.mode == "bez AI (model niedostępny)" and result.answer.startswith("Na początek")
    fake_model.reply.update(error=False, stop="refusal")
    assert (await kolba.answer(report, "x")).mode == "AI"


def test_offline_answers_from_report_facts_and_links(report):
    rain = kolba.offline_answer(report, "Ile spadło deszczu?")
    assert "mm" in rain.answer and "Sprawdź też" in rain.answer
    soil = kolba.offline_answer(report, "Jaka mam glebę?")
    assert report.soil.texture_topsoil in soil.answer
    permit = kolba.offline_answer(report, "Czy na studnię trzeba pozwolenie?")
    assert any("wody-polskie" in link.url for link in permit.links)
    unknown = kolba.offline_answer(report, "Kto wygrał mecz?")
    assert "nie znalazłam" in unknown.answer and unknown.links


def test_prompt_and_offline_texts_avoid_dashes(report):
    assert "–" not in PERSONA and "—" not in PERSONA
    for question in kolba.QUICK_QUESTIONS.values():
        assert "—" not in kolba.offline_answer(report, question).answer
    assert all(link.url.startswith("https://") for link in links.all_links())


async def test_real_sdk_request_shape(report, monkeypatch):
    seen = []
    message = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": "Woda jest, ale mało (E01)."}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }

    def handler(request):
        seen.append(request)
        return httpx2.Response(200, json=message)

    transport = httpx2.MockTransport(handler)
    sdk = anthropic.AsyncAnthropic(api_key="test-key", http_client=httpx2.AsyncClient(transport=transport))
    monkeypatch.setattr(kolba, "_client", lambda: sdk)
    monkeypatch.setattr(land_settings(), "anthropic_api_key", "test-key")
    result = await kolba.answer(report, "Co z wodą?")
    body = json.loads(seen[0].content)
    assert body["fallbacks"] == "default" and body["output_config"] == {"effort": "medium"}
    assert "server-side-fallback-2026-07-01" in seen[0].headers["anthropic-beta"]
    assert body["system"][2]["cache_control"] == {"type": "ephemeral"}
    assert result.mode == "AI" and result.evidence == ["E01"]
