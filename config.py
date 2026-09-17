"""
config.py
---------
Central configuration module for application and database settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent
_env_path = _project_root / ".env"
load_dotenv(dotenv_path=_env_path if _env_path.exists() else None)


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in {None, ""}:
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
    ssl_ca: str = field(default_factory=lambda: os.getenv("DB_SSL_CA", ""))
    ssl_cert: str = field(default_factory=lambda: os.getenv("DB_SSL_CERT", ""))
    ssl_key: str = field(default_factory=lambda: os.getenv("DB_SSL_KEY", ""))
    ssl_mode: str = field(default_factory=lambda: os.getenv("DB_SSL_MODE", ""))

    def __post_init__(self) -> None:
        for field_name in ("dialect", "host", "name", "user", "password", "ssl_ca", "ssl_cert", "ssl_key", "ssl_mode"):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, (value or "").strip())
        if not self.host:
            object.__setattr__(self, "host", "localhost")
        if not self.dialect:
            object.__setattr__(self, "dialect", "mysql")
        object.__setattr__(self, "dialect", self.dialect.lower())

    @classmethod
    def from_env(cls, prefix: str = "DB_") -> "DatabaseSettings":
        return cls(
            dialect=os.getenv(f"{prefix}DIALECT", "mysql"),
            host=os.getenv(f"{prefix}HOST", "localhost"),
            port=_get_int(f"{prefix}PORT", 3306),
            name=os.getenv(f"{prefix}NAME", ""),
            user=os.getenv(f"{prefix}USER", ""),
            password=os.getenv(f"{prefix}PASSWORD", ""),
            ssl_ca=os.getenv(f"{prefix}SSL_CA", ""),
            ssl_cert=os.getenv(f"{prefix}SSL_CERT", ""),
            ssl_key=os.getenv(f"{prefix}SSL_KEY", ""),
            ssl_mode=os.getenv(f"{prefix}SSL_MODE", ""),
        )

    @property
    def sqlalchemy_url(self) -> str:
        dialect = self.dialect
        if dialect in {"mysql", "mariadb"}:
            if not self.name:
                raise ValueError("DB_NAME is required for MySQL/MariaDB connections.")
            driver = "mysql+pymysql"
            auth = f"{quote_plus(self.user)}:{quote_plus(self.password)}@" if (self.user or self.password) else ""
            params = []
            if self.ssl_ca:
                params.append(f"ssl_ca={quote_plus(self.ssl_ca)}")
            if self.ssl_cert:
                params.append(f"ssl_cert={quote_plus(self.ssl_cert)}")
            if self.ssl_key:
                params.append(f"ssl_key={quote_plus(self.ssl_key)}")
            if self.ssl_mode:
                params.append(f"ssl_mode={quote_plus(self.ssl_mode)}")
            query = f"?{'&'.join(params)}" if params else ""
            return f"{driver}://{auth}{self.host}:{self.port}/{self.name}{query}"

        if dialect in {"postgres", "postgresql"}:
            if not self.name:
                raise ValueError("DB_NAME is required for PostgreSQL connections.")
            auth = f"{quote_plus(self.user)}:{quote_plus(self.password)}@" if (self.user or self.password) else ""
            params = []
            if self.ssl_mode:
                params.append(f"sslmode={quote_plus(self.ssl_mode)}")
            if self.ssl_ca:
                params.append(f"sslrootcert={quote_plus(self.ssl_ca)}")
            if self.ssl_cert:
                params.append(f"sslcert={quote_plus(self.ssl_cert)}")
            if self.ssl_key:
                params.append(f"sslkey={quote_plus(self.ssl_key)}")
            query = f"?{'&'.join(params)}" if params else ""
            return f"postgresql+psycopg2://{auth}{self.host}:{self.port}/{self.name}{query}"

        if dialect in {"mssql", "sqlserver"}:
            if not self.name:
                raise ValueError("DB_NAME is required for SQL Server connections.")
            auth = f"{quote_plus(self.user)}:{quote_plus(self.password)}@" if (self.user or self.password) else ""
            return f"mssql+pyodbc://{auth}{self.host}:{self.port}/{self.name}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

        if dialect == "oracle":
            if not self.name:
                raise ValueError("DB_NAME is required for Oracle connections.")
            return f"oracle+oracledb://{quote_plus(self.user)}:{quote_plus(self.password)}@{self.host}:{self.port}/?service_name={quote_plus(self.name)}"
        if dialect == "duckdb":
            return f"duckdb:///{Path(self.name or ':memory:').expanduser()}"
        if dialect == "snowflake":
            if not self.name:
                raise ValueError("DB_NAME is required for Snowflake connections.")
            return f"snowflake://{quote_plus(self.user)}:{quote_plus(self.password)}@{self.host}/{self.name}"
        if dialect in {"bigquery", "googlebigquery"}:
            return f"bigquery://{self.name}"
        if dialect == "sqlite":
            if self.name in {"", ":memory:"}:
                return "sqlite:///:memory:"
            return f"sqlite:///{Path(self.name).expanduser()}"
        raise ValueError(f"Unsupported DB_DIALECT: {self.dialect}")


@dataclass(frozen=True)
class LLMSettings:
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini"))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = field(default_factory=lambda: os.getenv("OPENROUTER_MODEL", ""))


@dataclass(frozen=True)
class AppSettings:
    env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    max_result_rows: int = field(default_factory=lambda: _get_int("MAX_RESULT_ROWS", 1000))
    query_timeout_seconds: int = field(default_factory=lambda: _get_int("QUERY_TIMEOUT_SECONDS", 15))
    max_sql_correction_attempts: int = field(default_factory=lambda: _get_int("MAX_SQL_CORRECTION_ATTEMPTS", 2))
    allowed_tables: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    app: AppSettings = field(default_factory=AppSettings)

    @property
    def database_profiles(self) -> dict[str, DatabaseSettings]:
        profiles = {"Default": self.database}
        names = [name.strip() for name in os.getenv("DB_PROFILES", "").split(",")]
        for name in names:
            if name:
                profiles[name] = DatabaseSettings.from_env(f"DB_{name.upper()}_")
        return profiles

    @property
    def all_database_profiles(self) -> dict[str, DatabaseSettings]:
        profiles = self.database_profiles
        default = self.database
        ports = {"MySQL": 3306, "MariaDB": 3306, "PostgreSQL": 5432, "SQLite": 0, "SQL Server": 1433, "Oracle": 1521, "DuckDB": 0, "Snowflake": 443, "BigQuery": 443}
        dialects = {"MySQL": "mysql", "MariaDB": "mariadb", "PostgreSQL": "postgresql", "SQLite": "sqlite", "SQL Server": "mssql", "Oracle": "oracle", "DuckDB": "duckdb", "Snowflake": "snowflake", "BigQuery": "bigquery"}
        for name, dialect in dialects.items():
            if name not in profiles:
                profiles[name] = DatabaseSettings(dialect=dialect, host=default.host, port=ports[name], name=default.name, user=default.user, password=default.password, ssl_ca=default.ssl_ca, ssl_cert=default.ssl_cert, ssl_key=default.ssl_key, ssl_mode=default.ssl_mode)
        return profiles


settings = Settings()
