from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import get_settings


class LandSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_prefix="WODIVA_", extra="ignore")

    land_budget_s: float = 20.0
    source_timeout_s: float = 12.0
    sat_history_years: int = 9
    sat_history_background: bool = True
    raster_concurrency: int = 16
    public_url: str = "http://localhost:8000"
    assistant_model: str = "claude-opus-5-5"
    assistant_effort: str = "medium"
    assistant_daily_limit: int = 300
    assistant_report_limit: int = 30
    assistant_max_tokens: int = 2000
    assistant_secret: str = ""
    assistant_provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0"
    ollama_num_ctx: int = 3072
    ollama_num_predict: int = 250
    ollama_timeout_s: float = 150.0
    ollama_keep_alive: str = "2h"
    ollama_use_mmap: bool = True
    ollama_num_thread: int = 0
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "WODIVA_ANTHROPIC_API_KEY")
    )


@lru_cache
def land_settings() -> LandSettings:
    return LandSettings()


def data_dir() -> Path:
    return get_settings().data_dir / "land"


def var_dir() -> Path:
    path = get_settings().cache_path.parent
    path.mkdir(parents=True, exist_ok=True)
    return path
