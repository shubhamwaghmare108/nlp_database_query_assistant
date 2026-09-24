"""
tests/test_query_service.py
------------------------------
End-to-end pipeline tests for services/query_service.py, with the
database, LLM, and schema layers all faked out so this suite runs
without any external dependencies (no MySQL, no API key needed).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.query_executor import QueryExecutionError, QueryExecutionResult  # noqa: E402
from database.schema import ColumnInfo, DatabaseSchema, TableInfo  # noqa: E402
from services import query_service  # noqa: E402


def _sample_schema() -> DatabaseSchema:
    schema = DatabaseSchema(database_name="sales_db")
    schema.tables["customers"] = TableInfo(
        name="customers",
        columns=[
            ColumnInfo("customer_id", "INT", is_primary_key=True),
            ColumnInfo("customer_name", "VARCHAR(100)"),
            ColumnInfo("city", "VARCHAR(100)"),
        ],
    )
    return schema


def test_empty_question_returns_friendly_error():
    response = query_service.answer_question("   ")
    assert not response.success
    assert "enter a question" in response.error_message.lower()


def test_successful_pipeline(monkeypatch):
    monkeypatch.setattr(query_service, "get_database_schema", lambda: _sample_schema())
    monkeypatch.setattr(query_service, "generate_sql", lambda **kwargs: "SELECT * FROM customers")

    fake_df = pd.DataFrame({"customer_id": [1, 2], "customer_name": ["A", "B"]})

    def fake_execute(sql, max_rows=None):
        return QueryExecutionResult(
            dataframe=fake_df, row_count=2, execution_time_seconds=0.01, truncated=False
        )

    monkeypatch.setattr(query_service, "execute_select_query", fake_execute)

    response = query_service.answer_question("Show all customers", generate_explanation=False)
    assert response.success
    assert response.row_count == 2
    assert "customers" in response.sql.lower()


def test_execution_failure_triggers_correction_then_fails(monkeypatch):
    monkeypatch.setattr(query_service, "get_database_schema", lambda: _sample_schema())
    monkeypatch.setattr(query_service, "generate_sql", lambda **kwargs: "SELECT * FROM customers")
    monkeypatch.setattr(query_service, "correct_sql", lambda **kwargs: "SELECT * FROM customers")

    def always_fail(sql, max_rows=None):
        raise QueryExecutionError("simulated failure")

    monkeypatch.setattr(query_service, "execute_select_query", always_fail)

    response = query_service.answer_question("Show all customers", generate_explanation=False)
    assert not response.success
    assert "simulated failure" in response.error_message


def test_invalid_sql_is_rejected_before_execution(monkeypatch):
    monkeypatch.setattr(query_service, "get_database_schema", lambda: _sample_schema())
    monkeypatch.setattr(query_service, "generate_sql", lambda **kwargs: "DROP TABLE customers")
    correction_called = {"called": False}

    def should_not_correct(**kwargs):
        correction_called["called"] = True
        raise AssertionError("correct_sql must not run after security validation failure")

    monkeypatch.setattr(query_service, "correct_sql", should_not_correct)

    called = {"executed": False}

    def should_not_run(sql, max_rows=None):
        called["executed"] = True
        raise AssertionError("execute_select_query should never be called for invalid SQL")

    monkeypatch.setattr(query_service, "execute_select_query", should_not_run)

    response = query_service.answer_question("Delete everything", generate_explanation=False)
    assert not response.success
    assert called["executed"] is False
    assert correction_called["called"] is False
