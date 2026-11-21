from datetime import UTC, datetime

from app.core.schemas import DataSource, SourceStatus

CATEGORY_LABELS = {
    "I": "bardzo podatna na suszę (gleby bardzo lekkie: piaski luźne i słabogliniaste)",
    "II": "podatna na suszę (gleby lekkie: piaski gliniaste)",
    "III": "średnio podatna na suszę (gleby średnie: gliny lekkie, pyły)",
    "IV": "mało podatna na suszę (gleby ciężkie: gliny średnie i ciężkie, iły)",
}


def data_source() -> DataSource:
    return DataSource(
        name="IUNG-PIB – kategorie podatności gleb na suszę i progi KBW (Dz.U. 2019 poz. 739)",
        url="https://susza.iung.pulawy.pl/mapa-kategorii/",
        license="Akt prawny (domena publiczna); metodyka IUNG-PIB",
        retrieved_at=datetime(2026, 11, 21, tzinfo=UTC),
        status=SourceStatus.partial,
        note="Mapa kategorii IUNG nie ma publicznego API – kategoria wyznaczana z uziarnienia wg kryteriów "
        "rozporządzenia; wyniki Monitoringu Suszy służą do walidacji (scripts/validate.py).",
    )
