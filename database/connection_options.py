"""DBAPI-specific SQLAlchemy connection options.

Keep provider/driver-specific connection arguments out of the generic
DatabaseSettings URL so one RDBMS's options cannot be passed accidentally
to another driver's DBAPI constructor.
"""
from __future__ import annotations

from config import DatabaseSettings


def _mysql_connect_args(settings: DatabaseSettings) -> dict:
    """Return PyMySQL SSL arguments without using unsupported ssl_mode."""
    args: dict = {}
    mode = settings.ssl_mode.strip().lower().replace("_", "-")

    if mode in {"disable", "disabled", "off", "none"}:
        args["ssl_disabled"] = True
        return args

    ssl_fields = {
        "ssl_ca": settings.ssl_ca,
        "ssl_cert": settings.ssl_cert,
        "ssl_key": settings.ssl_key,
    }
    for key, value in ssl_fields.items():
        if value:
            args[key] = value

    if mode in {"verify-ca", "verify-full", "verify-identity"}:
        if not settings.ssl_ca:
            raise ValueError(
                f"MySQL SSL mode '{settings.ssl_mode}' requires a CA certificate path."
            )
        args["ssl_verify_cert"] = True
        if mode in {"verify-full", "verify-identity"}:
            args["ssl_verify_identity"] = True
    elif mode in {"required", "require"} and not any(
        key in args for key in ("ssl_ca", "ssl_cert", "ssl_key")
    ):
        args["ssl"] = {}

    return args


def _postgres_connect_args(settings: DatabaseSettings) -> dict:
    """Return psycopg2 SSL options in DBAPI-native names."""
    args: dict = {}
    mode = settings.ssl_mode.strip().lower()
    if mode:
        args["sslmode"] = mode
    if settings.ssl_ca:
        args["sslrootcert"] = settings.ssl_ca
    if settings.ssl_cert:
        args["sslcert"] = settings.ssl_cert
    if settings.ssl_key:
        args["sslkey"] = settings.ssl_key
    return args


def _mssql_connect_args(settings: DatabaseSettings) -> dict:
    """Return pyodbc-only options that cannot be shared with other RDBMSs."""
    args: dict = {}
    if settings.encrypt:
        args["Encrypt"] = settings.encrypt
    if settings.trust_server_certificate:
        args["TrustServerCertificate"] = settings.trust_server_certificate
    if settings.authentication in {"windows", "trusted", "integrated"}:
        args["Trusted_Connection"] = "yes"
    return args


def build_connect_args(settings: DatabaseSettings) -> dict:
    """Build connection arguments for the selected dialect/driver."""
    d = settings.dialect
    driver = settings.driver

    if d in {"mysql", "mariadb"} and driver == "pymysql":
        return _mysql_connect_args(settings)

    if d in {"postgres", "postgresql"} and driver == "psycopg2":
        return _postgres_connect_args(settings)

    if d in {"mssql", "sqlserver"} and driver == "pyodbc":
        return _mssql_connect_args(settings)

    if d == "sqlite":
        return {"check_same_thread": False}

    return {}


def validate_connection_settings(settings: DatabaseSettings) -> None:
    """Validate settings that are specific enough to fail before connect()."""
    d = settings.dialect
    driver = settings.driver

    if d in {"mysql", "mariadb"} and driver != "pymysql":
        raise ValueError(
            f"Unsupported {d} driver '{driver}'. The configured adapter currently "
            "supports PyMySQL; use DB_DRIVER=pymysql."
        )

    if d in {"postgres", "postgresql"} and driver != "psycopg2":
        raise ValueError(
            f"Unsupported PostgreSQL driver '{driver}'. Use DB_DRIVER=psycopg2."
        )

    if d in {"mssql", "sqlserver"} and driver != "pyodbc":
        raise ValueError(
            f"Unsupported SQL Server driver '{driver}'. Use DB_DRIVER=pyodbc."
        )
