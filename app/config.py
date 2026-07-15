"""Configuration: env-based secrets/runtime via pydantic-settings, plus YAML tunables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime + secrets, read from environment / .env. Field names map to UPPER_SNAKE env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime
    portfolio_connector: str = "mock"          # "mock" (Phase 0) | "zerodha" (Phase 1+)
    portfolio_config: str = "config.yaml"
    database_url: str | None = None            # unset -> local SQLite

    # Zerodha / Kite (Phase 1+)
    kite_api_key: str | None = None
    kite_api_secret: str | None = None
    kite_user_id: str | None = None
    kite_password: str | None = None
    kite_totp_secret: str | None = None

    # LLM (Phase 4+) / Widget API (Phase 3+)
    anthropic_api_key: str | None = None
    widget_api_token: str | None = None
    # Soft monthly LLM-spend budget (USD). When set, /status flags over-budget so the ops
    # watchdog can nudge you to recharge your Anthropic account. None -> no budget tracking.
    monthly_budget_usd: float | None = None

    def resolved_database_url(self) -> str:
        """Return DATABASE_URL if set, else a local SQLite file under data/."""
        if self.database_url:
            return self.database_url
        data_dir = REPO_ROOT / "data"
        data_dir.mkdir(exist_ok=True)
        return f"sqlite:///{data_dir / 'portfolio.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_yaml_config(path: str | None = None) -> dict:
    """Load config.yaml; fall back to config.example.yaml so the app runs out of the box."""
    candidates = []
    if path:
        candidates.append(REPO_ROOT / path)
    candidates.append(REPO_ROOT / "config.yaml")
    candidates.append(REPO_ROOT / "config.example.yaml")
    for c in candidates:
        if c.exists():
            with c.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}
