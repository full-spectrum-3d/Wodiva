from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "dev"
    cors_origins: str = "*"
    data_dir: Path = BACKEND_DIR / "data"
    cache_path: Path = BACKEND_DIR / "var" / "cache.sqlite"
    era5_cube_path: Path = BACKEND_DIR / "var" / "era5_land_pl.zarr"
    era5_cube_url: str = ""
    era5_start: str = "2015-01-01"
    era5_lag_days: int = 5
    cdsapi_url: str = "https://cds.climate.copernicus.eu/api"
    cdsapi_key: str = ""
    openmeteo_api_key: str = ""
    parcels_parquet_url: str = (
        "https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/PARQUET/0_dzialki.parquet"
    )
    parcels_parquet_local: Path | None = None
    rate_limit_per_minute: int = 30
    analysis_years: int = 10
    http_timeout_s: float = 12.0
    analyze_mock: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
