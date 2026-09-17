"""
tests/test_database.py
------------------------
Tests for the database connection and query execution layer.

These tests use a local SQLite in-memory database (via a monkeypatched
engine) instead of a live MySQL server, so they can run in CI without
external dependencies. They exercise the same SQLAlchemy code paths
that query_executor.py uses against MySQL in production.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import query_executor  # noqa: E402


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE customers (id INTEGER, name TEXT, city TEXT)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Aarav', 'Mumbai')"))
        conn.execute(text("INSERT INTO customers VALUES (2, 'Priya', 'Pune')"))
        conn.commit()
    monkeypatch.setattr(query_executor, "get_engine", lambda: engine)
    return engine


def test_valid_select_returns_dataframe(sqlite_engine):
    result = query_executor.execute_select_query("SELECT * FROM customers")
    assert isinstance(result.dataframe, pd.DataFrame)
    assert result.row_count == 2
    assert not result.truncated


def test_empty_result_handled(sqlite_engine):
    result = query_executor.execute_select_query(
        "SELECT * FROM customers WHERE city = 'Nowhere'"
    )
    assert result.row_count == 0
    assert result.dataframe.empty


def test_invalid_query_raises_query_execution_error(sqlite_engine):
    with pytest.raises(query_executor.QueryExecutionError):
        query_executor.execute_select_query("SELECT * FROM nonexistent_table")


def test_row_limit_enforced(sqlite_engine):
    result = query_executor.execute_select_query("SELECT * FROM customers", max_rows=1)
    assert result.row_count == 1
    assert result.truncated is True
