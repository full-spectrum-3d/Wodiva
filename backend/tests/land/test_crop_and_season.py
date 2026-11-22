from datetime import date

from app.land import causes, service
from app.land.assessment import assess, level_from
from app.land.models import Level
from app.land.recommend import context, rules
from app.report import pdf

from .conftest import DAY

GRASS = "uzytki_zielone"
ARABLE_ONLY = {"AGR_COVER", "AGR_ORGANIC", "AGR_TILLAGE", "AGR_CONTOUR", "AGR_VARIETY", "AGR_KEEP"}


def _with_groundwater(land, quantity: str, risk: str):
    hydro = land.hydro.model_copy(
        update={"groundwater": {"body": {"code": "PLGW200054", "quantitative_status": quantity, "risk": risk}}}
    )
    return land.model_copy(update={"hydro": hydro})


def _ctx(crop, water, soil, irrigation, land, parcel, level):
    found = causes.identify(water, soil, land)
    return context.build(crop, DAY, True, parcel.area_ha, water, soil, irrigation, land, found, level)


def test_good_groundwater_at_risk_is_not_called_poor(parcel, water, soil, irrigation, land):
    land = _with_groundwater(land, "dobry", "zagrożona")
    result = service.interpret(parcel, water, soil, irrigation, service.to_core(land))
    titles = {r.title for r in result.recommendations}
    texts = " ".join(r.justification for r in result.recommendations)
    assert "Zasilaj wody podziemne retencją na działce" not in titles
    assert "Oszczędzaj wody podziemne" in titles
    assert "złym stanie" not in texts


def test_poor_groundwater_keeps_retention_priority(parcel, water, soil, irrigation, land):
    land = _with_groundwater(land, "słaby", "zagrożona")
    result = service.interpret(parcel, water, soil, irrigation, service.to_core(land))
    titles = {r.title for r in result.recommendations}
    assert "Zasilaj wody podziemne retencją na działce" in titles
    assert "Oszczędzaj wody podziemne" not in titles


def test_grassland_gets_no_tillage_or_catch_crops(parcel, water, soil, irrigation, land):
    for level in (Level.high, Level.low):
        ctx = _ctx(GRASS, water, soil, irrigation, land, parcel, level)
        keys = {r["key"] for r in rules.load_rules() if rules.matches(r, ctx)}
        assert not keys & ARABLE_ONLY
        texts = " ".join(rules.render(r["action"], ctx) for r in rules.load_rules() if rules.matches(r, ctx)).lower()
        for word in ("międzyplon", "orkę", "siew prowadź", "resztki pożniwne"):
            assert word not in texts
    high = _ctx(GRASS, water, soil, irrigation, land, parcel, Level.high)
    assert any(r["key"] == "AGR_GRASS_SWARD" and rules.matches(r, high) for r in rules.load_rules())


def test_arable_crop_still_gets_arable_rules(parcel, water, soil, irrigation, land):
    ctx = _ctx("pszenica_ozima", water, soil, irrigation, land, parcel, Level.high)
    keys = {r["key"] for r in rules.load_rules() if rules.matches(r, ctx)}
    assert "AGR_COVER" in keys and not any(k.startswith("AGR_GRASS") for k in keys)


def test_grassland_rules_render_without_placeholders(parcel, water, soil, irrigation, land):
    ctx = _ctx(GRASS, water, soil, irrigation, land, parcel, None)
    for rule in rules.load_rules():
        for field in ("action", "rationale"):
            assert "{" not in rules.render(rule[field], ctx)


def test_off_season_risk_is_capped_and_explained(water, land, monkeypatch):
    monkeypatch.setattr("app.land.assessment.level_from", lambda points: Level.high)
    winter = water.model_copy(update={"crop": GRASS, "analysis_date": date(2026, 11, 22)})
    result = assess(winter, land)
    assert result.risk_level == Level.medium
    assert "poza okresem wegetacji" in result.headline and "spoczynek zimowy" in result.headline
    summer = water.model_copy(update={"crop": GRASS, "analysis_date": date(2026, 7, 1)})
    assert assess(summer, land).risk_level == Level.high


def test_level_thresholds_unchanged():
    assert level_from(5) == Level.high and level_from(2.5) == Level.medium and level_from(0) == Level.low


def test_place_line_has_no_empty_fields(parcel):
    p = parcel.model_copy(
        update={
            "id": "141207_5.0016.158",
            "commune": "Halinów",
            "county": None,
            "voivodeship": None,
            "region": "KRZEWINA",
        }
    )
    line = pdf.place_line(p)
    assert ", ," not in line and ", ·" not in line
    assert line.startswith("Halinów, woj. mazowieckie · obręb KRZEWINA")
    bare = p.model_copy(update={"id": "", "commune": None, "region": None})
    assert pdf.place_line(bare) == f"{p.area_ha:.2f} ha"


def test_causes_title_follows_risk():
    assert pdf.causes_title("wysoka") == "2. Przyczyny niedoboru wody"
    assert pdf.causes_title("niska") == "2. Co ogranicza zapas wody na działce"
