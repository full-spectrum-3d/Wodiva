from pydantic import BaseModel


class Link(BaseModel):
    title: str
    url: str


GOV = "https://www.gov.pl/web/"

TOPICS: dict[str, tuple[tuple[str, ...], list[Link]]] = {
    "doplaty": (
        ("dopłat", "doplat", "ekoschemat", "arimr", "wpr", "płatnoś", "platnos", "wniosek o płat", "dotac"),
        [
            Link(
                title="ARiMR: płatności bezpośrednie i ekoschematy",
                url=GOV + "arimr/platnosci-bezposrednie-od-roku-2023",
            ),
            Link(title="ARiMR: Plan Strategiczny WPR 2023-2027", url=GOV + "arimr/plan-strategiczny-dla-wpr-2023-2028"),
            Link(title="ARiMR: biura powiatowe", url=GOV + "arimr/oddzialy-regionalne-i-biura-powiatowe"),
        ],
    ),
    "prawo_wodne": (
        ("pozwoleni", "wodnopraw", "zgłoszeni", "zgloszeni", "studni", "ujęci", "ujeci", "pobór", "pobor", "prawo"),
        [
            Link(title="Wody Polskie: pozwolenie wodnoprawne", url=GOV + "wody-polskie/pozwolenie-wodnoprawne"),
            Link(title="Wody Polskie: ocena wodnoprawna", url=GOV + "wody-polskie/ocena-wodnoprawna"),
            Link(
                title="Prawo wodne (ISAP)",
                url="https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20170001566",
            ),
        ],
    ),
    "susza_pomoc": (
        ("klęsk", "klesk", "straty", "stratę", "strat w", "odszkod", "pomoc suszow", "komisj", "oszacow"),
        [
            Link(title="MRiRW: pomoc suszowa", url=GOV + "rolnictwo/pomoc-suszowa"),
            Link(
                title="Wniosek o oszacowanie strat spowodowanych suszą",
                url=GOV + "rolnictwo/zloz-wniosek-o-oszacowanie-spowodowanych-przez-susze-strat-w-uprawach-rolnych",
            ),
            Link(title="MRiRW: monitoring suszy", url=GOV + "rolnictwo/monitoring-suszy"),
        ],
    ),
    "susza_monitoring": (
        ("susz", "smsr", "iung", "monitoring"),
        [
            Link(title="IUNG: System Monitoringu Suszy Rolniczej", url="https://susza.iung.pulawy.pl/"),
            Link(title="MRiRW: monitoring suszy", url=GOV + "rolnictwo/monitoring-suszy"),
        ],
    ),
    "pogoda": (
        ("pogod", "prognoz", "deszcz", "opad", "przymrozk", "upał", "upal", "burz", "temperatur"),
        [
            Link(title="IMGW-PIB: prognozy i ostrzeżenia", url="https://meteo.imgw.pl/"),
            Link(title="IMGW-PIB", url="https://www.imgw.pl/"),
        ],
    ),
    "rzeki": (
        ("rzek", "stan wód", "stan wod", "wezbr", "powód", "powod", "hydrolog"),
        [
            Link(title="IMGW-PIB: stany wód w rzekach", url="https://hydro.imgw.pl/"),
            Link(
                title="Wody Polskie: ochrona przed powodzią i suszą",
                url=GOV + "wody-polskie/ochrona-przed-powodzia-i-susza",
            ),
        ],
    ),
    "retencja": (
        ("retenc", "zatrzym", "oczk", "staw", "zastawk", "melior", "rów", "row ", "rowy", "spółk", "spolk"),
        [
            Link(title="Wody Polskie: Stop Suszy", url=GOV + "wody-polskie/stop-suszy"),
            Link(title="Program Stop Suszy", url="https://stopsuszy.pl/"),
            Link(title="Wody Polskie: kontakt z zarządami zlewni", url=GOV + "wody-polskie/kontakt"),
        ],
    ),
    "doradztwo": (
        ("doradc", "odr", "szkoleni", "porad", "agronom", "nawoż", "nawoz", "odmian", "siew", "płodozmian"),
        [
            Link(title="MRiRW: doradztwo rolnicze (ODR)", url=GOV + "rolnictwo/doradztwo-rolnicze2"),
            Link(title="Centrum Doradztwa Rolniczego", url="https://www.cdr.gov.pl/"),
            Link(title="IUNG-PIB", url="https://www.iung.pl/"),
        ],
    ),
    "mapy": (
        ("mapa", "mapy", "geoportal", "granic", "ewidencj"),
        [Link(title="Geoportal", url="https://www.geoportal.gov.pl/")],
    ),
    "wody_podziemne": (
        ("podziemn", "zwierciad", "hydrogeolog", "pig", "gzwp", "jcwpd"),
        [Link(title="PIG-PIB: Państwowa Służba Hydrogeologiczna", url="https://www.pgi.gov.pl/psh.html")],
    ),
    "kowr": (
        ("kowr", "dzierżaw", "dzierzaw", "grunty skarbu"),
        [Link(title="Krajowy Ośrodek Wsparcia Rolnictwa", url=GOV + "kowr")],
    ),
}

DEFAULT = [
    Link(title="MRiRW: doradztwo rolnicze (ODR)", url=GOV + "rolnictwo/doradztwo-rolnicze2"),
    Link(title="IUNG: System Monitoringu Suszy Rolniczej", url="https://susza.iung.pulawy.pl/"),
    Link(title="Wody Polskie", url=GOV + "wody-polskie"),
    Link(title="ARiMR", url=GOV + "arimr"),
]


def all_links() -> list[Link]:
    seen: dict[str, Link] = {}
    for _, links in TOPICS.values():
        for link in links:
            seen.setdefault(link.url, link)
    for link in DEFAULT:
        seen.setdefault(link.url, link)
    return list(seen.values())


def for_question(question: str, limit: int = 3) -> list[Link]:
    q = question.lower()
    found: dict[str, Link] = {}
    for words, links in TOPICS.values():
        if any(w in q for w in words):
            for link in links:
                found.setdefault(link.url, link)
    return list(found.values())[:limit]


def in_text(text: str) -> list[Link]:
    return [link for link in all_links() if link.url in text]


def catalog_text() -> str:
    return "\n".join(f"- {link.title}: {link.url}" for link in all_links())
