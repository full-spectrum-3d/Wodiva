import pytest

from app.core.schemas import Parcel, SourceStatus
from app.water import parcel as parcel_mod
from app.water.sources import egib, geocode, uldk

UUG_PAYLOAD = {
    "results": {
        "1": {
            "city": "Krzewina",
            "street": None,
            "number": "12",
            "jednostka": "{Polska,dolnośląskie,zgorzelecki,Bogatynia}",
            "x": "216386.14",
            "y": "357946.41",
        },
        "2": {
            "city": "Krzewina",
            "street": None,
            "number": "12",
            "jednostka": '{Polska,mazowieckie,miński,"Halinów"}',
            "x": "663570.33",
            "y": "486716.8",
        },
    }
}


def _parcel(parcel_id: str, commune: str = "Bogatynia", region: str = "Krzewina") -> Parcel:
    return Parcel(
        id=parcel_id,
        commune=commune,
        region=region,
        geometry_wkt_2180="POLYGON ((0 0, 100 0, 100 100, 0 100, 0 0))",
        geometry_geojson={"type": "Point", "coordinates": [0, 0]},
        area_ha=1.0,
        perimeter_m=400.0,
        centroid_lat=51.0,
        centroid_lon=15.0,
        size_class="średnia",
    )


def test_geocode_parse_and_label():
    found = geocode.parse(UUG_PAYLOAD)
    assert [a["commune"] for a in found] == ["Bogatynia", "Halinów"]
    assert found[0]["x"] == pytest.approx(216386.14)
    assert geocode.label(found[0]) == "Krzewina 12, gm. Bogatynia"
    assert geocode.query_text("Warszawa", "ul. Wspólna", "2") == "Warszawa, Wspólna 2"
    assert geocode.query_text("Krzewina", "", "12") == "Krzewina, 12"


def test_parse_regions():
    text = (
        "0\n022503_5.0003|Krzewina|Bogatynia|powiat zgorzelecki|dolnośląskie\n"
        "141207_5.0016|Krzewina|Halinów|powiat miński|mazowieckie\n"
    )
    rows = uldk.parse_regions(text)
    assert [r["teryt"] for r in rows] == ["022503_5.0003", "141207_5.0016"]
    with pytest.raises(uldk.ParcelNotFound):
        uldk.parse_regions("-1 brak wyników")


def test_same_place_ignores_case_diacritics_and_suffix():
    assert parcel_mod._same_place("Wiskitki-obszar wiejski", "wiskitki")
    assert parcel_mod._same_place("Halinów", "halinow")
    assert not parcel_mod._same_place("Bogatynia", "Halinów")
    assert parcel_mod._same_place("Bogatynia", "")


async def test_region_search_asks_to_choose_between_communes(monkeypatch):
    async def regions(name):
        return [
            {"teryt": "022503_5.0003", "region": name, "commune": "Bogatynia", "county": "powiat zgorzelecki"},
            {"teryt": "141207_5.0016", "region": name, "commune": "Halinów", "county": "powiat miński"},
        ]

    async def by_id(parcel_id):
        commune = "Bogatynia" if parcel_id.startswith("0225") else "Halinów"
        return [{"id": parcel_id, "commune": commune, "region": "Krzewina", "county": None}]

    monkeypatch.setattr(uldk, "regions", regions)
    monkeypatch.setattr(uldk, "by_id", by_id)
    with pytest.raises(parcel_mod.ParcelLookupError) as exc:
        await parcel_mod.resolve_by_region("Krzewina", "134")
    assert [c["id"] for c in exc.value.candidates] == ["022503_5.0003.134", "141207_5.0016.134"]


async def test_region_search_with_commune_resolves_one(monkeypatch):
    async def regions(name):
        return [
            {"teryt": "022503_5.0003", "region": name, "commune": "Bogatynia"},
            {"teryt": "141207_5.0016", "region": name, "commune": "Halinów"},
        ]

    async def by_id(parcel_id):
        return [{"id": parcel_id, "commune": "Halinów", "region": "Krzewina"}]

    resolved = []

    async def resolve_by_id(parcel_id, with_land_use=True):
        resolved.append(parcel_id)
        return _parcel(parcel_id, "Halinów"), []

    monkeypatch.setattr(uldk, "regions", regions)
    monkeypatch.setattr(uldk, "by_id", by_id)
    monkeypatch.setattr(parcel_mod, "resolve_by_id", resolve_by_id)
    found, _ = await parcel_mod.resolve_by_region("Krzewina", "134", "halinow")
    assert found.id == "141207_5.0016.134"
    assert resolved == ["141207_5.0016.134"]


async def test_typed_region_and_number_goes_through_region_search(monkeypatch):
    calls = []

    async def resolve_by_region(region, number, commune="", with_land_use=True):
        calls.append((region, number, commune))
        return _parcel("022503_5.0003.134"), []

    monkeypatch.setattr(parcel_mod, "resolve_by_region", resolve_by_region)
    await parcel_mod.resolve_by_id("Bogatynia, Krzewina 134")
    await parcel_mod.resolve_by_id("Krzewina 134/2")
    assert calls == [("Krzewina", "134", "Bogatynia"), ("Krzewina", "134/2", "")]


async def test_address_with_two_places_returns_candidates(monkeypatch):
    async def addresses(city, street, number):
        return geocode.parse(UUG_PAYLOAD)

    async def resolve_by_point(lat, lon, with_land_use=True):
        return _parcel("022503_5.0003.1" if lon < 18 else "141207_5.0016.7"), []

    monkeypatch.setattr(geocode, "addresses", addresses)
    monkeypatch.setattr(parcel_mod, "resolve_by_point", resolve_by_point)
    with pytest.raises(parcel_mod.ParcelLookupError) as exc:
        await parcel_mod.resolve_by_address("Krzewina", "", "12")
    labels = [c["label"] for c in exc.value.candidates]
    assert labels == ["Krzewina 12, gm. Bogatynia", "Krzewina 12, gm. Halinów"]

    found, sources, label = await parcel_mod.resolve_by_address("Krzewina", "", "12", "Bogatynia")
    assert found.id == "022503_5.0003.1"
    assert label == "Krzewina 12, gm. Bogatynia"
    assert sources[0].name.startswith("UUG")


async def test_land_use_checked_depends_on_kieg_answer(monkeypatch):
    async def unavailable(geom):
        return [], egib.data_source(SourceStatus.missing, egib.UNAVAILABLE)

    async def empty(geom):
        return [], egib.data_source(SourceStatus.missing, "brak informacji o użytkach w odpowiedzi WMS")

    monkeypatch.setattr(egib, "land_use", unavailable)
    checked = await parcel_mod._with_land_use(_parcel("x"), [])
    assert checked.is_agricultural is None and checked.land_use_checked is False
    monkeypatch.setattr(egib, "land_use", empty)
    checked = await parcel_mod._with_land_use(_parcel("x"), [])
    assert checked.is_agricultural is None and checked.land_use_checked is True
    checked = await parcel_mod._with_land_use(_parcel("x"), [], "RIVa,ŁIII")
    assert checked.is_agricultural is True and checked.land_use_checked is True
