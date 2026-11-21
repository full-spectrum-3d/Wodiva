import pytest

from app.assistant import kolba
from app.core.contracts import LandInterpretation, LandObservation, ReportInput
from app.land import causes, service
from app.land.assessment import assess
from app.land.recommend import rules
from app.land.sources import edo
from app.report import builder, pdf
from app.report.summary import summarize

from .conftest import CROP, DAY


def _report(parcel, water, soil, irrigation, land, interpretation=None):
    observation = service.to_core(land)
    interpretation = interpretation or service.interpret(parcel, water, soil, irrigation, observation)
    data = ReportInput(
        parcel=parcel,
        analysis_date=DAY,
        crop=CROP,
        water=water,
        soil=soil,
        irrigation=irrigation,
        land=observation,
        interpretation=interpretation,
        sources=observation.sources,
        limitations=[*observation.limitations, *interpretation.limitations],
        timings_s={},
    )
    return builder.build(data)


def test_observation_carries_fields_for_water_model(land):
    observation = service.to_core(land)
    assert observation.terrain.slope_mean_pct == 3.4
    assert observation.satellite.phase_offset_days == 6
    assert observation.satellite.surface_state == "roślinność"
    assert observation.terrain.depressions[0]["volume_m3"] == 60
    assert observation.hydro.ditches[0]["distance_m"] == 60
    assert observation.hydro.edo["cdi_class"] == "ostrzeżenie"
    back = service.from_core(observation)
    assert back.satellite.vci_ndvi == 0.18 and back.terrain.runoff_risk.value == "średnia"


def test_interpret_returns_ranked_causes_and_ordered_recommendations(parcel, water, soil, irrigation, land):
    result = service.interpret(parcel, water, soil, irrigation, service.to_core(land))
    assert [c.rank for c in result.causes] == list(range(1, len(result.causes) + 1))
    assert {c.code for c in result.causes} <= {"opad", "upał", "gleba", "spływ", "retencja"}
    categories = {r.category for r in result.recommendations}
    assert {"retencja", "agrotechnika"} <= categories
    depression = next(r for r in result.recommendations if r.title.startswith("Zatrzymaj wodę"))
    assert depression.location is not None and "?" not in depression.justification
    assert {c.section for c in result.confidence} >= {"ocena wilgotności", "satelita", "teren", "hydrologia"}


def test_scenarios_from_water_model_reach_recommendations(parcel, water, soil, irrigation, land):
    result = service.interpret(parcel, water, soil, irrigation, service.to_core(land))
    texts = " ".join(r.justification for r in result.recommendations)
    mulch = next(s for s in water.scenarios if s.code == "mulcz")
    assert f"w roku {mulch.reference_year}" in texts


def test_no_water_means_no_recommendations(parcel, soil, irrigation, land):
    result = service.interpret(parcel, None, soil, irrigation, service.to_core(land))
    assert result.causes == [] and result.recommendations == []
    report = _report(parcel, None, soil, irrigation, land, LandInterpretation())
    assert report.recommendations == [] and report.causes == []
    assert summarize(report).status == "brak"


def test_report_order_pdf_and_summary(parcel, water, soil, irrigation, land):
    report = _report(parcel, water, soil, irrigation, land)
    order = [r.category for r in report.recommendations]
    assert order == sorted(order, key=lambda c: builder.CATEGORY_ORDER[c])
    summary = summarize(report)
    assert summary.risk_level in ("wysoka", "średnia", "niska") and summary.findings
    content = pdf.render(report, None)
    assert content[:4] == b"%PDF" and len(content) > 5000


def test_causes_use_water_model_numbers(water, soil, land):
    found = {c.key: c for c in causes.identify(water, soil, land)}
    c = water.climate
    if c.precip_30d_norm_mm:
        assert found["opad"].contribution_mm == pytest.approx(max(c.precip_30d_norm_mm - c.precip_30d_mm, 0), abs=0.1)
    assert found["gleba"].active
    assert found["krajobraz"].active


def test_assessment_needs_water(land):
    assert assess(None, land).risk_level is None


def test_every_rule_renders_without_placeholders(parcel, water, soil, irrigation, land):
    from app.land.recommend import context

    found = causes.identify(water, soil, land)
    ctx = context.build(CROP, DAY, True, parcel.area_ha, water, soil, irrigation, land, found, None)
    for rule in rules.load_rules():
        for field in ("action", "rationale"):
            assert "{" not in rules.render(rule[field], ctx)


def test_rules_operators():
    assert rules.matches({"when": {"all": [{"field": "a", "op": "le", "value": 3}]}}, {"a": 2})
    assert not rules.matches({"when": {"all": [{"field": "a", "op": "le", "value": 3}]}}, {"a": None})
    assert rules.matches({"when": {"any": [{"field": "a", "op": "is_true"}, {"field": "b", "op": "exists"}]}}, {"b": 1})
    with pytest.raises(ValueError):
        rules.matches({"when": {"all": [{"field": "a", "op": "bad"}]}}, {"a": 1})
    assert rules.months_label([5, 6, 7]) == "maj–lipiec"


def test_edo_classification():
    assert edo.classify((220, 5, 12))[0] == "alarm"
    assert edo.classify((231, 160, 2))[0] == "ostrzeżenie"
    assert edo.classify((10, 120, 200))[0] == "inna klasa"
    assert str(edo.dekad_start(DAY)) == "2025-06-11"


def test_assistant_offline(parcel, water, soil, irrigation, land):
    report = _report(parcel, water, soil, irrigation, land)
    assert "główne przyczyny" in kolba.offline_answer(report, "Dlaczego moje pole jest suche?").answer.lower()
    assert kolba.offline_answer(report, "Co zrobić najpierw?").answer.startswith("Na początek")
    assert "gotowe pytania" in kolba.offline_answer(report, "Jaka pogoda w Paryżu?").answer


async def test_observe_uses_collect_and_keeps_artifacts(monkeypatch, parcel, land, artifacts):
    async def fake_collect(*args):
        return land, artifacts

    monkeypatch.setattr(service.collect, "collect", fake_collect)
    observation = await service.observe(parcel, DAY, CROP)
    assert isinstance(observation, LandObservation)
    assert service.artifacts_for(parcel.id, DAY) is artifacts
    assert any(s.name.startswith("Sentinel-2") for s in observation.sources)
