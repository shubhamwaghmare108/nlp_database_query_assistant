import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import DatabaseSettings, Settings  # noqa: E402


def test_supported_database_urls():
    cases = {
        "mysql": "mysql+pymysql://",
        "postgresql": "postgresql+psycopg2://",
        "mssql": "mssql+pyodbc://",
        "oracle": "oracle+oracledb://",
        "snowflake": "snowflake://",
        "bigquery": "bigquery://",
    }

    for dialect, prefix in cases.items():
        profile = DatabaseSettings(
            dialect=dialect,
            host="db.example.com",
            name="sales",
            user="reader",
            password="secret",
        )
        assert profile.sqlalchemy_url.startswith(prefix)

    assert DatabaseSettings(dialect="sqlite", name=":memory:").sqlalchemy_url == (
        "sqlite:///:memory:"
    )
    assert DatabaseSettings(dialect="duckdb", name="data.duckdb").sqlalchemy_url == (
        "duckdb:///data.duckdb"
    )

    snowflake = DatabaseSettings(
        dialect="snowflake",
        host="account.example",
        name="sales",
        user="reader",
        password="secret",
        schema="analytics",
        warehouse="compute_wh",
        role="analyst",
    )
    assert "warehouse=compute_wh" in snowflake.sqlalchemy_url
    assert "role=analyst" in snowflake.sqlalchemy_url


def test_named_database_profiles_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("DB_PROFILES", "warehouse")
    monkeypatch.setenv("DB_WAREHOUSE_DIALECT", "postgresql")
    monkeypatch.setenv("DB_WAREHOUSE_HOST", "warehouse.example.com")
    monkeypatch.setenv("DB_WAREHOUSE_PORT", "5432")
    monkeypatch.setenv("DB_WAREHOUSE_NAME", "sales")

    profiles = Settings().database_profiles

    assert set(profiles) == {"Default", "warehouse"}
    assert profiles["warehouse"].dialect == "postgresql"
    assert profiles["warehouse"].port == 5432

def test_default_profile_is_always_available(monkeypatch):
    monkeypatch.delenv("DB_PROFILES", raising=False)
    profiles = Settings().database_profiles
    assert set(profiles) == {"Default"}


def test_database_profile_driver_validation():
    from database.connection_options import validate_connection_settings

    supported = {
        "oracle": "oracledb",
        "snowflake": "snowflake",
        "bigquery": "bigquery",
        "duckdb": "duckdb_engine",
        "sqlite": "pysqlite",
    }
    for dialect, driver in supported.items():
        validate_connection_settings(DatabaseSettings(dialect=dialect, driver=driver))

    for dialect, driver in supported.items():
        try:
            validate_connection_settings(DatabaseSettings(dialect=dialect, driver="wrong"))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{dialect} should reject driver={driver!r}")
