from datetime import UTC, datetime

from app.core.schemas import DataSource, Limitation, SourceStatus
from app.land.models import DataStatus, LandNote, LandSourceNote

CATALOG: dict[str, dict[str, str]] = {
    "sentinel2": {
        "name": "Sentinel-2 L2A (pasma B03, B04, B05, B08, B8A, B11, SCL)",
        "provider": "Copernicus / ESA, katalog Earth Search (Element 84)",
        "url": "https://earth-search.aws.element84.com/v1",
        "license": (
            "Dane Copernicus Sentinel: bezpłatne i otwarte (Copernicus data policy, Rozporządzenie UE 1159/2013)"
        ),
    },
    "sentinel1": {
        "name": "Sentinel-1 GRD RTC (VV, VH)",
        "provider": "Copernicus / ESA, Microsoft Planetary Computer",
        "url": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc",
        "license": "Dane Copernicus Sentinel: bezpłatne i otwarte; produkt RTC: CC BY 4.0",
    },
    "landsat": {
        "name": "Landsat 5/7/8/9 Collection 2 Level-2 (red, nir08, swir16, qa_pixel)",
        "provider": "USGS / NASA, Microsoft Planetary Computer",
        "url": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2",
        "license": (
            "Dane USGS Landsat: domena publiczna, bez ograniczeń (prośba o podanie źródła: courtesy of the U.S. "
            "Geological Survey)"
        ),
    },
    "nmt": {
        "name": "Numeryczny Model Terenu (NMT) – usługa wysokości",
        "provider": "GUGiK (services.gugik.gov.pl/nmt, GetHByPointList)",
        "url": "https://services.gugik.gov.pl/nmt/",
        "license": "Dane PZGiK udostępniane bezpłatnie (ustawa Prawo geodezyjne i kartograficzne, art. 40a)",
    },
    "copdem": {
        "name": "Copernicus DEM GLO-30",
        "provider": "ESA / Copernicus, AWS Open Data",
        "url": "https://copernicus-dem-30m.s3.amazonaws.com/",
        "license": (
            "Copernicus DEM: bezpłatna licencja z obowiązkiem podania źródła (© DLR e.V. 2010-2014 i © Airbus "
            "Defence and Space GmbH 2014-2018, dostarczone w ramach programu Copernicus)"
        ),
    },
    "bdot10k": {
        "name": (
            "BDOT10k: cieki (z identyfikatorem MPHP), rowy melioracyjne, wody, mokradła, zadrzewienia, "
            "budowle hydrotechniczne"
        ),
        "provider": "GUGiK, Geoportal.gov.pl (WMS kompozycja BDOT10k)",
        "url": "https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer",
        "license": "Dane PZGiK udostępniane bezpłatnie (ustawa Prawo geodezyjne i kartograficzne, art. 40a)",
    },
    "pigpib": {
        "name": "Monitoring wód podziemnych, JCWPd, GZWP",
        "provider": "PIG-PIB, Państwowa Służba Hydrogeologiczna (cbdgmapa.pgi.gov.pl)",
        "url": "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/hydrogeologia",
        "license": "Dane PIG-PIB udostępniane publicznie, z podaniem źródła",
    },
    "edo": {
        "name": "Combined Drought Indicator (CDI) v4",
        "provider": "Copernicus Emergency Management Service, European Drought Observatory",
        "url": "https://drought.emergency.copernicus.eu/api/wms",
        "license": "Copernicus EMS: bezpłatne użycie z podaniem źródła",
    },
}

STATUS = {
    DataStatus.ok: SourceStatus.ok,
    DataStatus.partial: SourceStatus.partial,
    DataStatus.missing: SourceStatus.missing,
}
SEVERITY = {"info": "info", "ostrzeżenie": "ostrzeżenie", "krytyczne": "krytyczne"}


def to_source(note: LandSourceNote) -> DataSource:
    meta = CATALOG[note.key]
    return DataSource(
        name=f"{meta['name']} – {meta['provider']}",
        url=meta["url"],
        license=meta["license"],
        retrieved_at=datetime.now(UTC),
        period_start=note.period_start,
        period_end=note.period_end,
        status=STATUS[note.status],
        note=note.note,
    )


def to_limitation(note: LandNote) -> Limitation:
    return Limitation(
        code=note.code, message=note.text, severity=SEVERITY.get(note.severity, "info"), section=note.section
    )
