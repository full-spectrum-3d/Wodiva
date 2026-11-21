import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

PARCEL_ID_RE = re.compile(r"^\d{6}_\d\.\d{4}(\.AR_\d{1,4})?\.[0-9A-Za-z/]{1,20}$")
REGION_NUMBER_RE = re.compile(r"^[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż .\-]{2,60}\s+[0-9]{1,6}(/[0-9]{1,4})?$")


POLAND_TZ = ZoneInfo("Europe/Warsaw")


class InputError(ValueError):
    pass


def normalize_parcel_id(raw: str) -> str:
    value = raw.strip()
    value = re.sub(r"\s+", " ", value)
    compact = value.replace(" ", "")
    compact = re.sub(r"(?i)\.ar[_\-]?(\d+)", lambda m: f".AR_{m.group(1)}", compact)
    compact = compact.replace(",", ".")
    m = re.match(r"^(\d{6})[_\-.]?(\d)[.\-](\d{1,4})((?:\.AR_\d{1,4})?)[.\-](.+)$", compact)
    if m:
        commune, kind, region, sheet, number = m.groups()
        candidate = f"{commune}_{kind}.{int(region):04d}{sheet}.{number}"
        if PARCEL_ID_RE.match(candidate):
            return candidate
    if REGION_NUMBER_RE.match(value):
        return value
    raise InputError("Nieprawidłowy identyfikator działki. Przykład: 141201_1.0001.6509 albo 'Krzewina 134'.")


def is_full_parcel_id(value: str) -> bool:
    return bool(PARCEL_ID_RE.match(value))


def today_in_poland() -> date:
    return datetime.now(POLAND_TZ).date()


def validate_analysis_date(value: date, today: date | None = None) -> date:
    today = today or today_in_poland()
    years = get_settings().analysis_years
    try:
        earliest = today.replace(year=today.year - years)
    except ValueError:
        earliest = today.replace(year=today.year - years, day=28) + timedelta(days=1)
    if value > today:
        raise InputError("Data analizy nie może być z przyszłości.")
    if value < earliest:
        raise InputError(f"Data analizy musi mieścić się w ostatnich {years} latach (od {earliest.isoformat()}).")
    return value


def validate_lat_lon(lat: float, lon: float) -> tuple[float, float]:
    if not (48.9 <= lat <= 55.0 and 14.0 <= lon <= 24.3):
        raise InputError("Punkt leży poza obszarem Polski.")
    return lat, lon
