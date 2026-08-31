from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated, environment-first runtime configuration."""

    # CORS is deliberately supplied as a human-friendly comma-separated environment
    # variable, so do not apply Pydantic's default JSON decoding for list settings.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", enable_decoding=False)

    app_name: str = "SentinelFlow API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./data/sentinelflow.db"
    redis_url: str | None = None
    model_path: Path = Path("artifacts/production/model_bundle.joblib")
    metrics_path: Path = Path("artifacts/production/metrics.json")
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    # Demo mode is intentionally local-only.  It exists to make the synthetic demo
    # usable, never as an authentication scheme for a deployed service.
    demo_auth_enabled: bool = True
    auth_mode: Literal["demo", "oidc"] = "demo"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_roles_claim: str = "roles"
    oidc_organization_claim: str = "organization_id"
    demo_organization_id: str = "org_demo"
    demo_organization_name: str = "SentinelFlow Synthetic Demo"
    # Application startup must not mutate a production schema. Tests and an
    # explicitly local convenience environment may opt into metadata creation.
    schema_management: Literal["migrate", "create_all"] = "create_all"
    expected_schema_revision: str = "0002_operations_foundation"
    rate_limit_per_minute: int = Field(default=120, ge=10, le=10_000)
    request_max_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    log_level: str = "INFO"
    feature_version: str = "pit-v1"
    model_version: str = "untrained-demo"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            AnyHttpUrl(origin)
        return value

    @model_validator(mode="after")
    def validate_deployment_mode(self) -> Settings:
        if self.environment in {"staging", "production"}:
            if self.demo_auth_enabled or self.auth_mode == "demo":
                raise ValueError(
                    "demo authentication cannot be enabled outside development or test"
                )
            if self.auth_mode != "oidc":
                raise ValueError("staging and production require OIDC authentication")
            if not all((self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)):
                raise ValueError(
                    "OIDC issuer, audience, and JWKS URL are required outside development"
                )
            if self.schema_management == "create_all":
                raise ValueError("production schema management must use Alembic migrations")
        if self.auth_mode == "demo" and not self.demo_auth_enabled:
            raise ValueError("auth_mode=demo requires demo_auth_enabled=true")
        if self.auth_mode == "oidc" and self.demo_auth_enabled:
            raise ValueError("demo_auth_enabled must be false when OIDC authentication is selected")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
