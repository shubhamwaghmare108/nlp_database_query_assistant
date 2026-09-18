"""Central configuration for application and database settings."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _default_driver(dialect: str) -> str:
    return {
        "mysql": "pymysql",
        "mariadb": "pymysql",
        "postgres": "psycopg2",
        "postgresql": "psycopg2",
        "mssql": "pyodbc",
        "sqlserver": "pyodbc",
        "oracle": "oracledb",
        "snowflake": "snowflake",
        "bigquery": "bigquery",
        "googlebigquery": "bigquery",
        "sqlite": "pysqlite",
        "duckdb": "duckdb_engine",
    }.get(dialect, "")


@dataclass(frozen=True)
class DatabaseSettings:
    dialect: str = field(default_factory=lambda: os.getenv("DB_DIALECT", "mysql"))
    driver: str = field(default_factory=lambda: os.getenv("DB_DRIVER", ""))
    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: _int("DB_PORT", 3306))
    name: str = field(default_factory=lambda: os.getenv("DB_NAME", ""))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", ""))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    ssl_ca: str = field(default_factory=lambda: os.getenv("DB_SSL_CA", ""))
    ssl_cert: str = field(default_factory=lambda: os.getenv("DB_SSL_CERT", ""))
    ssl_key: str = field(default_factory=lambda: os.getenv("DB_SSL_KEY", ""))
    ssl_mode: str = field(default_factory=lambda: os.getenv("DB_SSL_MODE", ""))
    authentication: str = field(default_factory=lambda: os.getenv("DB_AUTHENTICATION", "sql"))
    warehouse: str = field(default_factory=lambda: os.getenv("DB_WAREHOUSE", ""))
    schema: str = field(default_factory=lambda: os.getenv("DB_SCHEMA", ""))
    role: str = field(default_factory=lambda: os.getenv("DB_ROLE", ""))
    project_id: str = field(default_factory=lambda: os.getenv("DB_PROJECT_ID", ""))
    dataset: str = field(default_factory=lambda: os.getenv("DB_DATASET", ""))
    credentials_file: str = field(default_factory=lambda: os.getenv("DB_CREDENTIALS_FILE", ""))
    read_only: bool = field(default_factory=lambda: _bool("DB_READ_ONLY"))
    oracle_identifier: str = field(default_factory=lambda: os.getenv("DB_ORACLE_IDENTIFIER", "service_name"))
    odbc_driver: str = field(
        default_factory=lambda: os.getenv("DB_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    )
    encrypt: str = field(default_factory=lambda: os.getenv("DB_ENCRYPT", ""))
    trust_server_certificate: str = field(
        default_factory=lambda: os.getenv("DB_TRUST_SERVER_CERTIFICATE", "")
    )

    def __post_init__(self) -> None:
        text_fields = (
            "dialect", "driver", "host", "name", "user", "password",
            "ssl_ca", "ssl_cert", "ssl_key", "ssl_mode", "authentication",
            "warehouse", "schema", "role", "project_id", "dataset",
            "credentials_file", "oracle_identifier", "odbc_driver",
            "encrypt", "trust_server_certificate",
        )
        for key in text_fields:
            object.__setattr__(self, key, (getattr(self, key) or "").strip())

        object.__setattr__(self, "host", self.host or "localhost")
        object.__setattr__(self, "dialect", (self.dialect or "mysql").lower())
        object.__setattr__(self, "driver", (self.driver or _default_driver(self.dialect)).lower())
        object.__setattr__(self, "authentication", self.authentication.lower() or "sql")
        object.__setattr__(self, "oracle_identifier", self.oracle_identifier.lower() or "service_name")

    @classmethod
    def from_env(cls, prefix: str = "DB_") -> "DatabaseSettings":
        return cls(
            dialect=os.getenv(f"{prefix}DIALECT", "mysql"),
            driver=os.getenv(f"{prefix}DRIVER", ""),
            host=os.getenv(f"{prefix}HOST", "localhost"),
            port=_int(f"{prefix}PORT", 3306),
            name=os.getenv(f"{prefix}NAME", ""),
            user=os.getenv(f"{prefix}USER", ""),
            password=os.getenv(f"{prefix}PASSWORD", ""),
            ssl_ca=os.getenv(f"{prefix}SSL_CA", ""),
            ssl_cert=os.getenv(f"{prefix}SSL_CERT", ""),
            ssl_key=os.getenv(f"{prefix}SSL_KEY", ""),
            ssl_mode=os.getenv(f"{prefix}SSL_MODE", ""),
            authentication=os.getenv(f"{prefix}AUTHENTICATION", "sql"),
            warehouse=os.getenv(f"{prefix}WAREHOUSE", ""),
            schema=os.getenv(f"{prefix}SCHEMA", ""),
            role=os.getenv(f"{prefix}ROLE", ""),
            project_id=os.getenv(f"{prefix}PROJECT_ID", ""),
            dataset=os.getenv(f"{prefix}DATASET", ""),
            credentials_file=os.getenv(f"{prefix}CREDENTIALS_FILE", ""),
            read_only=_bool(f"{prefix}READ_ONLY"),
            oracle_identifier=os.getenv(f"{prefix}ORACLE_IDENTIFIER", "service_name"),
            odbc_driver=os.getenv(
                f"{prefix}ODBC_DRIVER", "ODBC Driver 18 for SQL Server"
            ),
            encrypt=os.getenv(f"{prefix}ENCRYPT", ""),
            trust_server_certificate=os.getenv(
                f"{prefix}TRUST_SERVER_CERTIFICATE", ""
            ),
        )

    @property
    def sqlalchemy_url(self) -> str:
        """Build only the SQLAlchemy URL.

        DBAPI-specific connection options are intentionally handled by
        database.connection_options instead of leaking unsupported parameters
        through the URL.
        """
        d = self.dialect
        driver = self.driver or _default_driver(d)

        if d in {"mysql", "mariadb"}:
            if not self.name:
                raise ValueError("Database name is required for MySQL/MariaDB.")
            auth = (
                f"{quote_plus(self.user)}:{quote_plus(self.password)}@"
                if (self.user or self.password) else ""
            )
            url_dialect = "mysql" if d == "mariadb" and driver == "pymysql" else d
            return (
                f"{url_dialect}+{driver}://{auth}{self.host}:{self.port}/"
                f"{quote_plus(self.name)}"
            )

        if d in {"postgres", "postgresql"}:
            if not self.name:
                raise ValueError("Database name is required for PostgreSQL.")
            auth = (
                f"{quote_plus(self.user)}:{quote_plus(self.password)}@"
                if (self.user or self.password) else ""
            )
            return (
                f"postgresql+{driver}://{auth}{self.host}:{self.port}/"
                f"{quote_plus(self.name)}"
            )

        if d in {"mssql", "sqlserver"}:
            if not self.name:
                raise ValueError("Database name is required for SQL Server.")
            auth = (
                ""
                if self.authentication in {"windows", "trusted", "integrated"}
                else f"{quote_plus(self.user)}:{quote_plus(self.password)}@"
            )
            params = [("driver", self.odbc_driver)]
            if self.encrypt:
                params.append(("Encrypt", self.encrypt))
            if self.trust_server_certificate:
                params.append(
                    ("TrustServerCertificate", self.trust_server_certificate)
                )
            if self.authentication in {"windows", "trusted", "integrated"}:
                params.append(("trusted_connection", "yes"))
            query = "&".join(
                f"{quote_plus(key)}={quote_plus(value)}" for key, value in params
            )
            return (
                f"mssql+{driver}://{auth}{self.host}:{self.port}/"
                f"{quote_plus(self.name)}?{query}"
            )

        if d == "oracle":
            if not self.name:
                raise ValueError("Service name or SID is required for Oracle.")
            identifier = "sid" if self.oracle_identifier == "sid" else "service_name"
            return (
                f"oracle+{driver}://{quote_plus(self.user)}:{quote_plus(self.password)}"
                f"@{self.host}:{self.port}/?{identifier}={quote_plus(self.name)}"
            )

        if d == "snowflake":
            if not self.host or not self.name:
                raise ValueError("Snowflake account and database are required.")
            path = quote_plus(self.name) + (
                f"/{quote_plus(self.schema)}" if self.schema else ""
            )
            return (
                f"snowflake://{quote_plus(self.user)}:{quote_plus(self.password)}"
                f"@{self.host}/{path}"
            )

        if d in {"bigquery", "googlebigquery"}:
            project = self.project_id or self.name
            if not project:
                raise ValueError("BigQuery project ID is required.")
            return (
                f"bigquery://{quote_plus(project)}"
                + (f"/{quote_plus(self.dataset)}" if self.dataset else "")
                + (
                    f"?credentials_path={quote_plus(self.credentials_file)}"
                    if self.credentials_file else ""
                )
            )

        if d == "duckdb":
            return (
                f"duckdb:///{Path(self.name or ':memory:').expanduser()}"
                + ("?read_only=true" if self.read_only else "")
            )

        if d == "sqlite":
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
    max_result_rows: int = field(default_factory=lambda: _int("MAX_RESULT_ROWS", 1000))
    query_timeout_seconds: int = field(default_factory=lambda: _int("QUERY_TIMEOUT_SECONDS", 15))
    max_sql_correction_attempts: int = field(default_factory=lambda: _int("MAX_SQL_CORRECTION_ATTEMPTS", 2))
    allowed_tables: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    app: AppSettings = field(default_factory=AppSettings)

    @property
    def database_profiles(self) -> dict[str, DatabaseSettings]:
        return {
            name: DatabaseSettings.from_env(f"DB_{name.upper()}_")
            for name in (x.strip() for x in os.getenv("DB_PROFILES", "").split(","))
            if name
        }

    @property
    def all_database_profiles(self) -> dict[str, DatabaseSettings]:
        return self.database_profiles


settings = Settings()
