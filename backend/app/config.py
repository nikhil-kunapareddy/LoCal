"""Application settings, loaded from the environment.

Secrets and tunables live here so the rest of the app never touches ``os.environ``
directly. ``pydantic-settings`` reads from the process environment and an optional
``.env`` file (see ``.env.example``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # External data-source credentials. All optional: a missing key degrades the
    # corresponding section of the payload rather than failing the whole request.
    noaa_token: Optional[str] = None
    eia_api_key: Optional[str] = None
    nrel_api_key: str = "DEMO_KEY"
    waqi_token: Optional[str] = None
    attom_api_key: Optional[str] = None
    fred_api_key: Optional[str] = None

    # Outbound HTTP behavior.
    request_timeout_seconds: float = 10.0

    # Only this origin (the Next.js proxy) is allowed to call the API in the
    # proxy topology. Comma-separated if more than one is ever needed.
    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def missing_optional_keys(self) -> list[str]:
        """Names of credentials that are unset, for a startup degraded-mode log."""
        checks = {
            "NOAA_TOKEN": self.noaa_token,
            "EIA_API_KEY": self.eia_api_key,
            "WAQI_TOKEN": self.waqi_token,
            "ATTOM_API_KEY": self.attom_api_key,
            "FRED_API_KEY": self.fred_api_key,
        }
        return [name for name, value in checks.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
