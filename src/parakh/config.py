"""Settings from environment variables and a .env file (C6.1).

Field names map to upper-case variables: `anthropic_api_key` reads ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_VAR = "PARAKH_ENV_FILE"
REPO_ROOT = Path(__file__).resolve().parents[2]


def env_file() -> Path | None:
    """The .env file to read, if any."""
    override = os.environ.get(ENV_FILE_VAR)
    if override:
        return Path(override)
    local = Path(os.environ.get("DOTENV_PATH", ".env"))
    if local.exists():
        return local
    # D10 (v1.17): the repo sits inside the OneDrive "Stock Analysis" folder, and the
    # private .env stays one level up, outside the repo (D19).
    parent = REPO_ROOT.parent / ".env"
    return parent if parent.exists() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "dev"  # dev | test | staging | prod

    # LLM
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-5"
    llm_max_iterations: int = 8  # hard cap on every agent loop (C3.1)
    llm_timeout_s: float = 60
    llm_retry_attempts: int = 4
    llm_retry_min_wait_s: float = 1
    llm_retry_max_wait_s: float = 30
    llm_price_input_per_mtok: float = 3.0
    llm_price_output_per_mtok: float = 15.0
    confidence_review_below: float = 0.6
    max_usd_per_run: float = 1.0
    max_llm_calls_per_minute: int = 30

    # Tracing (C4.1)
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Supabase
    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None

    # Production secrets (C6.4)
    aws_region: str = "ap-south-1"

    # Paths (plan 04 §3.3). Defaults sit inside the repo; both are git-ignored or tracked as noted.
    # config/*.yaml (tracked); default <repo>/config
    parakh_config_dir: Path | None = None
    # audit outbox, run manifests, caches (git-ignored); default <repo>/state
    parakh_state_dir: Path | None = None
    # plan 13 D19: your private files (CAS PDFs, exports) stay in OneDrive, outside the repo
    parakh_inbox_dir: Path | None = None

    # Project-specific
    cas_password: SecretStr | None = None
    # plan 13 P6: key behind account_ref hashes; must stay stable once lots are stored
    parakh_account_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: SecretStr | None = None
    supabase_db_password: SecretStr | None = None


def config_dir() -> Path:
    """Where config/*.yaml lives (PARAKH_CONFIG_DIR overrides)."""
    return get_settings().parakh_config_dir or REPO_ROOT / "config"


def state_dir() -> Path:
    """Where local state lives: audit outbox, run manifests (PARAKH_STATE_DIR overrides)."""
    return get_settings().parakh_state_dir or REPO_ROOT / "state"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    path = env_file()
    return Settings(_env_file=path) if path else Settings()  # pyright: ignore[reportCallIssue]
