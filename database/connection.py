"""
Database connection management for the multi-RDBMS query platform.

This module is the single place that creates SQLAlchemy engines. Provider-
specific connection arguments are built by connection_options.py so a
MySQL/PyMySQL option cannot accidentally be passed to another DBAPI.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import DatabaseSettings, settings
from database.connection_options import build_connect_args, validate_connection_settings
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when an engine cannot be created for a database profile."""


@lru_cache(maxsize=16)
def get_engine(profile: DatabaseSettings | None = None) -> Engine:
    """Create or reuse an engine for the selected database profile."""
    db_settings = profile or settings.database

    try:
        if not getattr(db_settings, "name", "") and db_settings.dialect not in {
            "sqlite",
            "duckdb",
            "bigquery",
        }:
            raise ValueError("Database name is required for this RDBMS.")

        validate_connection_settings(db_settings)

        engine_kwargs = {"pool_pre_ping": True, "future": True}

        if db_settings.dialect not in {"sqlite", "duckdb", "bigquery"}:
            engine_kwargs.update(pool_recycle=1800, pool_size=5, max_overflow=5)

        connect_args = build_connect_args(db_settings)
        if connect_args:
            engine_kwargs["connect_args"] = connect_args

        engine = create_engine(db_settings.sqlalchemy_url, **engine_kwargs)
        logger.info(
            "Database engine created: dialect=%s driver=%s host=%s database=%s",
            db_settings.dialect,
            db_settings.driver,
            db_settings.host,
            db_settings.name,
        )
        return engine
    except Exception as exc:
        logger.exception(
            "Failed to create database engine for dialect=%s driver=%s",
            db_settings.dialect,
            db_settings.driver,
        )
        raise DatabaseConnectionError(str(exc)) from exc


def test_connection(profile: DatabaseSettings | None = None) -> bool:
    """Return whether the selected profile can execute a lightweight query."""
    try:
        engine = get_engine(profile)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection test succeeded for %s", engine.dialect.name)
        return True
    except Exception as exc:
        logger.warning("Database connection test failed: %s", exc)
        return False


def dispose_engine() -> None:
    """Clear cached engines; new connections will be created on demand."""
    get_engine.cache_clear()
