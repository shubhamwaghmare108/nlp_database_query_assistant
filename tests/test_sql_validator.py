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


def test_mixed_aggregate_query_is_limited():
    result = validate_sql(
        "SELECT customer_id, COUNT(*) FROM customers GROUP BY customer_id",
        allowed_tables=ALLOWED_TABLES,
    )
    assert result.is_valid
    assert "LIMIT 500" in result.sanitized_sql.upper()


def test_cte_alias_is_not_treated_as_unknown_table():
    result = validate_sql(
        """
        WITH recent_orders AS (
            SELECT * FROM orders
        )
        SELECT * FROM recent_orders
        """,
        allowed_tables=ALLOWED_TABLES,
    )
    assert result.is_valid
    assert "LIMIT 500" in result.sanitized_sql.upper()


def test_multiple_cte_aliases_are_not_treated_as_tables():
    result = validate_sql(
        """
        WITH recent_orders AS (
            SELECT * FROM orders
        ),
        customer_orders AS (
            SELECT c.customer_id
            FROM customers c
            JOIN recent_orders r ON c.customer_id = r.customer_id
        )
        SELECT * FROM customer_orders
        """,
        allowed_tables=ALLOWED_TABLES,
    )
    assert result.is_valid


def test_schema_qualified_table_is_allowed():
    result = validate_sql(
        "SELECT * FROM analytics.customers",
        allowed_tables={"analytics.customers"},
        dialect="postgresql",
    )
    assert result.is_valid


def test_catalog_qualified_table_is_allowed():
    result = validate_sql(
        "SELECT * FROM project.analytics.customers",
        allowed_tables={"project.analytics.customers"},
        dialect="bigquery",
    )
    assert result.is_valid


def test_qualified_unknown_table_is_rejected():
    result = validate_sql(
        "SELECT * FROM analytics.secret_table",
        allowed_tables={"analytics.customers"},
        dialect="postgresql",
    )
    assert not result.is_valid
    assert "analytics.secret_table" in result.errors[0]


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


def test_unapproved_system_table_rejected():
    result = validate_sql("SELECT * FROM performance_schema.events_statements")
    assert not result.is_valid


def test_bigquery_information_schema_tables_is_allowed():
    result = validate_sql(
        "SELECT * FROM project.region-us.INFORMATION_SCHEMA.TABLES",
        dialect="bigquery",
    )
    assert result.is_valid


def test_bigquery_information_schema_columns_is_allowed():
    result = validate_sql(
        "SELECT * FROM project.analytics.INFORMATION_SCHEMA.COLUMNS",
        dialect="bigquery",
    )
    assert result.is_valid


def test_bigquery_unapproved_system_table_is_rejected():
    result = validate_sql(
        "SELECT * FROM project.analytics.pg_catalog.secret_table",
        dialect="bigquery",
    )
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


def test_union_query_is_capped():
    result = validate_sql(
        "SELECT id FROM customers UNION SELECT id FROM orders",
        allowed_tables=ALLOWED_TABLES,
    )
    assert result.is_valid
    assert "LIMIT 500" in result.sanitized_sql.upper()


def test_invalid_default_limit_is_rejected():
    result = validate_sql(
        "SELECT * FROM customers",
        allowed_tables=ALLOWED_TABLES,
        default_limit=0,
    )
    assert not result.is_valid
