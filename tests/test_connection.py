"""Tests for provider-specific database connection configuration."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import DatabaseSettings  # noqa: E402
from database.connection import get_engine  # noqa: E402
from database.connection_options import build_connect_args  # noqa: E402


def test_mysql_does_not_put_ssl_mode_in_pymysql_url():
    profile = DatabaseSettings(
        dialect="mysql",
        host="db.example.com",
        port=3306,
        name="app",
        user="reader",
        password="secret",
        ssl_mode="required",
        ssl_ca="/certs/ca.pem",
    )
    assert "ssl_mode" not in profile.sqlalchemy_url
    assert "ssl_ca" not in profile.sqlalchemy_url
    args = build_connect_args(profile)
    assert args["ssl_ca"] == "/certs/ca.pem"
    assert "ssl_mode" not in args


def test_mysql_required_without_certificate_enables_tls():
    profile = DatabaseSettings(
        dialect="mysql",
        host="db.example.com",
        port=3306,
        name="app",
        user="reader",
        password="secret",
        ssl_mode="required",
    )
    assert build_connect_args(profile) == {"ssl": {}}


def test_mysql_verify_identity_requires_ca():
    profile = DatabaseSettings(
        dialect="mysql",
        host="db.example.com",
        port=3306,
        name="app",
        user="reader",
        password="secret",
        ssl_mode="verify-identity",
    )
    with pytest.raises(ValueError, match="requires a CA certificate"):
        build_connect_args(profile)


def test_postgres_keeps_sslmode_semantics_in_dbapi_args():
    profile = DatabaseSettings(
        dialect="postgresql",
        host="db.example.com",
        port=5432,
        name="app",
        user="reader",
        password="secret",
        ssl_mode="verify-full",
        ssl_ca="/certs/root.crt",
    )
    args = build_connect_args(profile)
    assert args["sslmode"] == "verify-full"
    assert args["sslrootcert"] == "/certs/root.crt"
    assert "ssl_mode" not in profile.sqlalchemy_url


def test_mssql_uses_odbc_specific_arguments_only():
    profile = DatabaseSettings(
        dialect="mssql",
        host="db.example.com",
        port=1433,
        name="app",
        authentication="windows",
        encrypt="yes",
        trust_server_certificate="no",
    )
    args = build_connect_args(profile)
    assert args == {}
    assert "driver=ODBC+Driver+18+for+SQL+Server" in profile.sqlalchemy_url
    assert "Encrypt=yes" in profile.sqlalchemy_url
    assert "TrustServerCertificate=no" in profile.sqlalchemy_url
    assert "trusted_connection=yes" in profile.sqlalchemy_url


def test_default_drivers_are_provider_specific():
    assert DatabaseSettings(dialect="mysql").driver == "pymysql"
    assert DatabaseSettings(dialect="postgresql").driver == "psycopg2"
    assert DatabaseSettings(dialect="mssql").driver == "pyodbc"
    assert DatabaseSettings(dialect="oracle").driver == "oracledb"
    assert DatabaseSettings(dialect="snowflake").driver == "snowflake"
    assert DatabaseSettings(dialect="bigquery").driver == "bigquery"


def test_get_engine_passes_connect_args(monkeypatch):
    captured = {}

    class FakeEngine:
        pass

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeEngine()

    monkeypatch.setattr("database.connection.create_engine", fake_create_engine)
    profile = DatabaseSettings(
        dialect="mysql",
        host="db.example.com",
        port=3306,
        name="app",
        user="reader",
        password="secret",
        ssl_mode="required",
    )
    engine = get_engine.__wrapped__(profile)
    assert isinstance(engine, FakeEngine)
    assert captured["kwargs"]["connect_args"] == {"ssl": {}}
    assert "ssl_mode" not in captured["url"]
