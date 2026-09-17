"""
tests/test_sql_generator.py
-----------------------------
Tests for nlp/sql_generator.py using a fake LLM client so no real API
calls or API keys are required to run the test suite.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.schema import ColumnInfo, DatabaseSchema, TableInfo  # noqa: E402
from nlp import sql_generator  # noqa: E402
from nlp.llm_client import LLMError  # noqa: E402


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
    schema.tables["orders"] = TableInfo(
        name="orders",
        columns=[
            ColumnInfo("order_id", "INT", is_primary_key=True),
            ColumnInfo("customer_id", "INT"),
            ColumnInfo("amount", "DECIMAL(12,2)"),
        ],
    )
    return schema


class FakeLLMClient:
    def __init__(self, response_text: str):
        self._response_text = response_text

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        return self._response_text


def test_generate_sql_returns_clean_sql(monkeypatch):
    fake = FakeLLMClient("```sql\nSELECT * FROM customers\n```")
    monkeypatch.setattr(sql_generator, "get_llm_client", lambda: fake)

    sql = sql_generator.generate_sql(_sample_schema(), "Show all customers")
    assert sql == "SELECT * FROM customers"


def test_generate_sql_raises_on_unanswerable(monkeypatch):
    fake = FakeLLMClient("UNANSWERABLE")
    monkeypatch.setattr(sql_generator, "get_llm_client", lambda: fake)

    with pytest.raises(sql_generator.SQLGenerationError):
        sql_generator.generate_sql(_sample_schema(), "What is the meaning of life?")


def test_generate_sql_wraps_llm_error(monkeypatch):
    class RaisingClient:
        def generate(self, *args, **kwargs):
            raise LLMError("API unavailable")

    monkeypatch.setattr(sql_generator, "get_llm_client", lambda: RaisingClient())

    with pytest.raises(sql_generator.SQLGenerationError):
        sql_generator.generate_sql(_sample_schema(), "Show all customers")


def test_select_relevant_tables_falls_back_to_all_when_no_match():
    schema = _sample_schema()
    tables = sql_generator.select_relevant_tables(schema, "asdkjhaskjdh nonsense query")
    assert set(tables) == set(schema.table_names())


def test_select_relevant_tables_matches_keywords():
    schema = _sample_schema()
    tables = sql_generator.select_relevant_tables(schema, "total order amount by customer")
    assert "orders" in tables
    assert "customers" in tables
