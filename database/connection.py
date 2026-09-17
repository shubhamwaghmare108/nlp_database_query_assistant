"""
database/connection.py
-----------------------
Owns the SQLAlchemy Engine and connection pooling. This is the only
module that should construct an Engine — everything else (schema
extraction, query execution) borrows a connection from here.

The engine is built from config.settings, so switching from MySQL to
PostgreSQL later only requires changing DB_DIALECT and the driver
resolution in config.DatabaseSettings.sqlalchemy_url — no changes here.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when the application cannot establish a database connection."""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """
    Return a process-wide singleton SQLAlchemy Engine with connection
    pooling. Cached so repeated calls (e.g. from Streamlit re-runs)
    reuse the same pool instead of opening new ones.
    """
    try:
        db_settings = settings.database
        if not getattr(db_settings, "name", "") and db_settings.dialect != "sqlite":
            raise ValueError("Database settings are incomplete: DB_NAME is required.")
        url = db_settings.sqlalchemy_url
        engine = create_engine(
            url,
            pool_pre_ping=True,   # detect stale connections
            pool_recycle=1800,    # recycle connections every 30 min
            pool_size=5,
            max_overflow=5,
            future=True,
        )
        logger.info(
            "Database engine created for host=%s db=%s dialect=%s",
            db_settings.host,
            db_settings.name,
            db_settings.dialect,
        )
        return engine
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("Failed to create database engine: %s", exc)
        raise DatabaseConnectionError(str(exc)) from exc


def test_connection() -> bool:
    """Ping the database. Returns True if reachable, False otherwise."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection test succeeded")
        return True
    except SQLAlchemyError as exc:
        logger.error("Database connection test failed: %s", exc)
        return False


def dispose_engine() -> None:
    """Dispose of the engine's connection pool (used in tests/shutdown)."""
    get_engine.cache_clear()
