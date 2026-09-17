"""
config.py
---------
Central configuration module. Loads all settings from environment
variables (via a .env file in local development) and exposes them
as a single, typed Settings object.

No other module should call os.getenv() directly — everything goes
through this module so configuration stays in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Load the project-level .env explicitly so the app still finds its config
# when started from a different working directory (e.g. a service manager).
_project_root = Path(__file__).resolve().parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class DatabaseSettings:
    dialect: str = field(default_factory=lambda: os.getenv("DB_DIALECT", "mysql"))
    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: _get_int("DB_PORT", 3306))
    name: str = field(default_factory=lambda: os.getenv("DB_NAME", ""))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", ""))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))

    def __post_init__(self) -> None:
        object.__setattr__(self, "dialect", (self.dialect or "mysql").strip().lower())
        object.__setattr__(self, "host", (self.host or "localhost").strip())
        object.__setattr__(self, "name", (self.name or "").strip())
        object.__setattr__(self, "user", (self.user or "").strip())
        object.__setattr__(self, "password", (self.password or "").strip())

    @property
    def sqlalchemy_url(self) -> str:
        """
        Build a SQLAlchemy connection URL. Supports MySQL, PostgreSQL, and
        SQLite, and URL-encodes credentials so special characters do not
        break the DSN.
        """
        dialect = self.dialect.lower()
        if dialect in {"mysql", "mariadb"}:
            driver = "mysql+pymysql"
            if not self.name:
                raise ValueError("DB_NAME is required for MySQL/PostgreSQL connections.")
            auth = (
                f"{quote_plus(self.user)}:{quote_plus(self.password)}"
                if self.user or self.password
                else ""
            )
            credentials = f"{auth}@" if auth else ""
            return (
                f"{driver}://{credentials}{self.host}:{self.port}/{self.name}"
            )
        if dialect in {"postgres", "postgresql"}:
            driver = "postgresql+psycopg2"
            if not self.name:
                raise ValueError("DB_NAME is required for MySQL/PostgreSQL connections.")
            auth = (
                f"{quote_plus(self.user)}:{quote_plus(self.password)}"
                if self.user or self.password
                else ""
            )
            credentials = f"{auth}@" if auth else ""
            return (
                f"{driver}://{credentials}{self.host}:{self.port}/{self.name}"
            )
        if dialect == "sqlite":
            if self.name in {"", ":memory:"}:
                return "sqlite:///:memory:"
            db_path = str(Path(self.name).expanduser())
            return f"sqlite:///{db_path}"
        raise ValueError(f"Unsupported DB_DIALECT: {self.dialect}")


@dataclass(frozen=True)
class LLMSettings:
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini"))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    )
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    openrouter_model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "")
    )


@dataclass(frozen=True)
class AppSettings:
    env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    max_result_rows: int = field(default_factory=lambda: _get_int("MAX_RESULT_ROWS", 1000))
    query_timeout_seconds: int = field(
        default_factory=lambda: _get_int("QUERY_TIMEOUT_SECONDS", 15)
    )
    max_sql_correction_attempts: int = field(
        default_factory=lambda: _get_int("MAX_SQL_CORRECTION_ATTEMPTS", 2)
    )
    # Tables the app is explicitly allowed to expose to the LLM / execute
    # queries against. Empty list = discover dynamically from schema and
    # allow all non-system tables.
    allowed_tables: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    app: AppSettings = field(default_factory=AppSettings)


settings = Settings()
