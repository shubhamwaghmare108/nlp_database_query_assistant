"""
tests/test_sql_validator.py
----------------------------
Unit tests for security/sql_validator.py. These are the most important
tests in the project: they prove destructive statements are rejected
regardless of what the LLM produces.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security.sql_validator import validate_sql  # noqa: E402

ALLOWED_TABLES = {"customers", "orders", "products", "order_items", "employees"}


def test_simple_select_passes():
    result = validate_sql("SELECT * FROM customers", allowed_tables=ALLOWED_TABLES)
    assert result.is_valid
    assert "LIMIT" in result.sanitized_sql.upper()


def test_select_with_join_passes():
    sql = (
        "SELECT c.city, SUM(o.amount) FROM customers c "
        "JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.city"
    )
    result = validate_sql(sql, allowed_tables=ALLOWED_TABLES)
    assert result.is_valid


def test_aggregate_only_query_not_force_limited():
    result = validate_sql("SELECT COUNT(*) FROM customers", allowed_tables=ALLOWED_TABLES)
    assert result.is_valid


def test_insert_is_rejected():
    result = validate_sql("INSERT INTO customers (customer_name) VALUES ('x')")
    assert not result.is_valid


def test_update_is_rejected():
    result = validate_sql("UPDATE customers SET city='X' WHERE customer_id=1")
    assert not result.is_valid


def test_delete_is_rejected():
    result = validate_sql("DELETE FROM customers WHERE customer_id=1")
    assert not result.is_valid


def test_drop_is_rejected():
    result = validate_sql("DROP TABLE customers")
    assert not result.is_valid


def test_alter_is_rejected():
    result = validate_sql("ALTER TABLE customers ADD COLUMN foo INT")
    assert not result.is_valid


def test_truncate_is_rejected():
    result = validate_sql("TRUNCATE TABLE customers")
    assert not result.is_valid


def test_multiple_statements_rejected():
    result = validate_sql("SELECT * FROM customers; DROP TABLE customers;")
    assert not result.is_valid


def test_unknown_table_rejected():
    result = validate_sql("SELECT * FROM secret_table", allowed_tables=ALLOWED_TABLES)
    assert not result.is_valid


def test_allowed_metadata_table_with_dialect_is_supported():
    result = validate_sql(
        "SELECT * FROM information_schema.tables",
        dialect="mysql",
    )
    assert result.is_valid


def test_system_table_rejected():
    result = validate_sql("SELECT * FROM information_schema.tables")
    assert not result.is_valid


def test_empty_sql_rejected():
    result = validate_sql("")
    assert not result.is_valid


def test_existing_limit_preserved_not_duplicated():
    result = validate_sql(
        "SELECT * FROM customers LIMIT 10", allowed_tables=ALLOWED_TABLES
    )
    assert result.is_valid
    assert result.sanitized_sql.upper().count("LIMIT") == 1
