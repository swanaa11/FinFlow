"""Configuration loading for FinFlow.

All runtime configuration is environment-driven (12-factor style). Paths derive
from a single *repo root* so the package never relies on the caller's working
directory. Secrets are read only from the environment / `.env` — never from
files inside the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_MARKER = "pyproject.toml"


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upwards from *start* (default: CWD) until a repo marker is found.

    Raises FileNotFoundError when no marker exists, so misconfigured callers
    fail fast instead of writing data into surprise locations.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / _REPO_MARKER).exists():
            return candidate
    raise FileNotFoundError(
        f"Could not locate repo root: no {_REPO_MARKER} found in or above {current}. "
        "Set FINFLOW_ROOT to the repository path."
    )


class Settings(BaseSettings):
    """Typed application settings, sourced from `FINFLOW_*` env vars / `.env`."""

    model_config = SettingsConfigDict(
        env_prefix="FINFLOW_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- runtime ---
    env: str = "dev"
    log_level: str = "INFO"
    timezone: str = "Asia/Kolkata"

    # --- paths (relative values resolve against the repo root) ---
    root: Path = Field(default_factory=find_repo_root)
    data_dir: Path = Path("data")
    db_path: Path = Path("data/finflow.duckdb")

    # --- safety switches ---
    demo_mode: bool = False
    demo_db_path: Path = Path("data/demo/finflow_demo.duckdb")
    notify_enabled: bool = False

    # --- notifications: Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.root / path)

    # Derived, always-absolute paths -----------------------------------------
    @property
    def data_path(self) -> Path:
        return self._resolve(self.data_dir)

    @property
    def db_file(self) -> Path:
        return self._resolve(self.db_path)

    @property
    def active_db_file(self) -> Path:
        """The database in use: demo DB when DEMO_MODE is enabled (fail-safe)."""
        return self._resolve(self.demo_db_path) if self.demo_mode else self.db_file

    @property
    def incoming_dir(self) -> Path:
        return self.data_path / "incoming"

    @property
    def raw_dir(self) -> Path:
        return self.data_path / "raw"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_path / "quarantine"

    @property
    def sample_dir(self) -> Path:
        return self.data_path / "sample"

    @property
    def backups_dir(self) -> Path:
        return self.data_path / "backups"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    # --- secrets are non-empty only when notifications are usable ---
    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token) and bool(self.telegram_chat_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance (call sites should use this)."""
    return Settings()
