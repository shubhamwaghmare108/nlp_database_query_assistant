"""
security/sql_validator.py
--------------------------
Defense-in-depth validation of LLM-generated SQL before it is
executed against the database.

The validator allows:
- SELECT statements
- WITH ... SELECT statements
- UNION queries
- Approved metadata queries for supported RDBMS systems

The validator rejects:
- INSERT, UPDATE, DELETE
- DDL operations such as DROP, ALTER, CREATE, TRUNCATE
- Multiple SQL statements
- Dangerous functions and commands
- Unauthorized tables
- Unapproved system tables
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

import sqlglot
from sqlglot import exp

from utils.logging_config import get_logger


logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

_ALLOWED_ROOT_EXPRESSIONS = (
    exp.Select,
    exp.With,
    exp.Union,
)

_DENIED_KEYWORDS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
    r"\bMERGE\b",
    r"\bREPLACE\b",
    r"\bLOAD_FILE\b",
    r"\bINTO\s+OUTFILE\b",
    r"\bINTO\s+DUMPFILE\b",
    r"\bSLEEP\s*\(",
    r"\bBENCHMARK\s*\(",
    r"\bxp_cmdshell\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bPRAGMA\b",
]

_DENIED_PATTERN = re.compile(
    "|".join(_DENIED_KEYWORDS),
    re.IGNORECASE,
)

# These prefixes identify system or metadata schemas.
_SYSTEM_TABLE_PREFIXES = (
    "information_schema",
    "performance_schema",
    "mysql.",
    "sys.",
    "pg_",
)

# Metadata tables that are explicitly allowed for each RDBMS.
#
# The values use the normalized names produced by sqlglot.
_ALLOWED_METADATA_TABLES = {
    "mysql": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "mariadb": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "postgres": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "postgresql": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "sqlite": {
        "sqlite_master",
        "sqlite_temp_master",
    },
    "oracle": {
        "user_tables",
        "user_tab_columns",
    },
    "sqlserver": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "tsql": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "duckdb": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "snowflake": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "bigquery": {
        "information_schema.tables",
        "information_schema.columns",
    },
    "googlebigquery": {
        "information_schema.tables",
        "information_schema.columns",
    },
}

_DEFAULT_LIMIT = 500


# ---------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------

@dataclass
class ValidationResult:
    """
    Result returned by validate_sql().
    """

    is_valid: bool
    sanitized_sql: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------
# Dialect helpers
# ---------------------------------------------------------------------

def _normalize_dialect(dialect: str) -> str:
    """
    Normalize the application database dialect.
    """
    return (dialect or "mysql").strip().lower()


def _parser_dialect(dialect: str) -> str:
    """
    Return the sqlglot parser dialect for an application RDBMS name.

    sqlglot parses MariaDB SQL using the MySQL dialect.
    """
    normalized = _normalize_dialect(dialect)

    if normalized == "mariadb":
        return "mysql"

    if normalized == "postgresql":
        return "postgres"

    if normalized == "sqlserver":
        return "tsql"

    return normalized


def _allowed_metadata_tables(dialect: str) -> Set[str]:
    """
    Return the explicitly approved metadata tables for a dialect.
    """
    normalized = _normalize_dialect(dialect)
    return set(_ALLOWED_METADATA_TABLES.get(normalized, set()))


# ---------------------------------------------------------------------
# SQL inspection helpers
# ---------------------------------------------------------------------

def _extract_cte_names(parsed: exp.Expression) -> Set[str]:
    """Return CTE aliases so they are not mistaken for physical tables."""
    return {
        cte.alias_or_name.lower()
        for cte in parsed.find_all(exp.CTE)
        if cte.alias_or_name
    }


def _extract_table_names(parsed: exp.Expression) -> Set[str]:
    """
    Extract unqualified physical table names.

    CTE aliases are excluded because they are query-local names, not
    database tables that need to appear in the connected schema.
    """
    cte_names = _extract_cte_names(parsed)
    return {
        table.name.lower()
        for table in parsed.find_all(exp.Table)
        if table.name and table.name.lower() not in cte_names
    }


def _extract_qualified_table_names(
    parsed: exp.Expression,
) -> Set[str]:
    """
    Extract qualified table names.

    Examples:
        customers
        information_schema.tables
        public.customers
    """
    names: Set[str] = set()

    for table in parsed.find_all(exp.Table):
        if not table.name:
            continue

        table_name = table.name.lower()
        database = table.args.get("db")
        catalog = table.args.get("catalog")

        parts = []
        if catalog and catalog.name:
            parts.append(catalog.name.lower())
        if database and database.name:
            parts.append(database.name.lower())
        parts.append(table_name)

        names.add(".".join(parts))

    return names


def _has_multiple_statements(sql: str) -> bool:
    """
    Reject multiple SQL statements separated by semicolons.

    A single trailing semicolon is allowed.
    """
    stripped = sql.strip().rstrip(";")
    return ";" in stripped


def _is_allowed_metadata_reference(
    table_name: str,
    qualified_tables: Set[str],
    allowed_metadata_tables: Set[str],
    dialect: str = "mysql",
) -> bool:
    """
    Determine whether an extracted table name belongs to an approved
    metadata table.

    BigQuery INFORMATION_SCHEMA views are commonly qualified with a
    project and region/dataset, for example:
        project.region-us.INFORMATION_SCHEMA.TABLES
        project.analytics.INFORMATION_SCHEMA.COLUMNS

    Those fully-qualified forms are approved only when their final two
    components are INFORMATION_SCHEMA.TABLES or COLUMNS.
    """
    if table_name in allowed_metadata_tables:
        return True

    normalized_dialect = _normalize_dialect(dialect)

    if normalized_dialect in {"bigquery", "googlebigquery"}:
        metadata_aliases = {
            "tables",
            "columns",
        }
        if table_name in metadata_aliases:
            return any(
                parts[-2:] == ["information_schema", table_name]
                for qualified_table in qualified_tables
                for parts in [qualified_table.lower().split(".")]
                if len(parts) >= 2
            )

    metadata_aliases = {
        metadata_table.rsplit(".", 1)[-1]
        for metadata_table in allowed_metadata_tables
    }

    if table_name not in metadata_aliases:
        return False

    return any(
        qualified_table in allowed_metadata_tables
        for qualified_table in qualified_tables
    )


def _contains_forbidden_operation(parsed: exp.Expression) -> bool:
    """
    Check the parsed AST for forbidden SQL operations.
    """
    forbidden_node_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.Command,
    )

    return any(
        parsed.find(node_type)
        for node_type in forbidden_node_types
    )


def _is_aggregate_only_query(parsed: exp.Expression) -> bool:
    """
    Aggregate-only queries do not need an automatic LIMIT clause.

    Examples:
        SELECT COUNT(*) FROM customers
        SELECT AVG(age) FROM customers
    """
    if not isinstance(parsed, exp.Select):
        return False

    if parsed.find(exp.Group) is not None:
        return False

    aggregate_types = (
        exp.Count,
        exp.Sum,
        exp.Avg,
        exp.Max,
        exp.Min,
    )

    # A query is aggregate-only only when every selected expression is
    # aggregate-based or a constant.  Merely containing one aggregate
    # must not disable the row limit for mixed queries such as:
    # SELECT customer_id, COUNT(*) FROM customers.
    for expression in parsed.expressions:
        if isinstance(expression, exp.Alias):
            expression = expression.this

        if isinstance(expression, exp.Star):
            return False

        if any(
            isinstance(node, exp.Column)
            for node in expression.find_all(exp.Column)
        ):
            return False

        if not any(
            isinstance(node, aggregate_types)
            for node in expression.find_all(exp.AggFunc)
        ):
            continue

    return any(
        isinstance(node, aggregate_types)
        for node in parsed.find_all(exp.AggFunc)
    )


# ---------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------

def validate_sql(
    sql: str,
    allowed_tables: Optional[Set[str]] = None,
    dialect: str = "mysql",
    default_limit: int = _DEFAULT_LIMIT,
) -> ValidationResult:
    """
    Validate and sanitize generated SQL.

    Parameters
    ----------
    sql:
        SQL generated by the LLM.

    allowed_tables:
        Set of application tables available in the connected database.
        Example:
            {"customers", "orders", "products"}

    dialect:
        Database dialect, such as:
            mysql, mariadb, postgres, sqlite, oracle, sqlserver

    default_limit:
        Automatic row limit for non-aggregate SELECT queries.

    Returns
    -------
    ValidationResult
    """
    errors: List[str] = []
    warnings: List[str] = []

    # -------------------------------------------------------------
    # Basic validation
    # -------------------------------------------------------------

    if not sql or not sql.strip():
        return ValidationResult(
            is_valid=False,
            errors=["Generated SQL is empty."],
        )

    if _has_multiple_statements(sql):
        return ValidationResult(
            is_valid=False,
            errors=["Multiple SQL statements are not allowed."],
        )

    if _DENIED_PATTERN.search(sql):
        return ValidationResult(
            is_valid=False,
            errors=[
                "The query contains a disallowed keyword or function."
            ],
        )

    # -------------------------------------------------------------
    # Parse SQL
    # -------------------------------------------------------------

    parser_dialect = _parser_dialect(dialect)

    try:
        parsed = sqlglot.parse_one(
            sql,
            read=parser_dialect,
        )
    except Exception as exc:
        logger.warning("SQL failed to parse: %s", exc)

        return ValidationResult(
            is_valid=False,
            errors=[
                f"The generated SQL is not valid: {exc}"
            ],
        )

    # -------------------------------------------------------------
    # Root expression validation
    # -------------------------------------------------------------

    if not isinstance(parsed, _ALLOWED_ROOT_EXPRESSIONS):
        return ValidationResult(
            is_valid=False,
            errors=[
                "Only SELECT, UNION, or WITH ... SELECT statements "
                "are permitted."
            ],
        )

    if _contains_forbidden_operation(parsed):
        return ValidationResult(
            is_valid=False,
            errors=[
                "The query contains a disallowed operation."
            ],
        )

    # -------------------------------------------------------------
    # Table extraction
    # -------------------------------------------------------------

    referenced_tables = _extract_table_names(parsed)
    qualified_tables = _extract_qualified_table_names(parsed)

    allowed_metadata_tables = _allowed_metadata_tables(dialect)

    # -------------------------------------------------------------
    # System-table validation
    # -------------------------------------------------------------

    for table in qualified_tables:
        normalized_table = table.lower()
        is_system_table = any(
            normalized_table == prefix.rstrip(".")
            or normalized_table.startswith(prefix)
            for prefix in _SYSTEM_TABLE_PREFIXES
        )

        if (
            is_system_table
            and normalized_table not in allowed_metadata_tables
            and not _is_allowed_metadata_reference(
                table_name=normalized_table.rsplit(".", 1)[-1],
                qualified_tables=qualified_tables,
                allowed_metadata_tables=allowed_metadata_tables,
                dialect=dialect,
            )
        ):
            return ValidationResult(
                is_valid=False,
                errors=[
                    f"Access to system table '{table}' is not allowed."
                ],
            )

    # SQLite and Oracle metadata tables do not necessarily use a
    # qualified schema name, so validate them separately.
    for table in referenced_tables:
        if table in {"sqlite_master", "sqlite_temp_master"}:
            if table not in allowed_metadata_tables:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        f"Access to system table '{table}' is not allowed."
                    ],
                )

        if table in {"user_tables", "user_tab_columns"}:
            if table not in allowed_metadata_tables:
                return ValidationResult(
                    is_valid=False,
                    errors=[
                        f"Access to system table '{table}' is not allowed."
                    ],
                )

    # -------------------------------------------------------------
    # Known-schema validation
    # -------------------------------------------------------------

    if allowed_tables is not None:
        normalized_allowed_tables = {
            table.lower()
            for table in allowed_tables
        }

        unknown_tables: Set[str] = set()

        cte_names = _extract_cte_names(parsed)

        for table_node in parsed.find_all(exp.Table):
            table_name = table_node.name.lower() if table_node.name else ""
            if not table_name or table_name in cte_names:
                continue

            database = table_node.args.get("db")
            catalog = table_node.args.get("catalog")
            parts = []
            if catalog and catalog.name:
                parts.append(catalog.name.lower())
            if database and database.name:
                parts.append(database.name.lower())
            parts.append(table_name)

            qualified_name = ".".join(parts)
            allowed = (
                table_name in normalized_allowed_tables
                or qualified_name in normalized_allowed_tables
            )

            if allowed:
                continue

            if _is_allowed_metadata_reference(
                table_name=table_name,
                qualified_tables=qualified_tables,
                allowed_metadata_tables=allowed_metadata_tables,
                dialect=dialect,
            ):
                continue

            unknown_tables.add(qualified_name)

        if unknown_tables:
            return ValidationResult(
                is_valid=False,
                errors=[
                    "The query references tables that are not part "
                    "of the known schema: "
                    + ", ".join(sorted(unknown_tables))
                ],
            )

    # -------------------------------------------------------------
    # Automatic LIMIT handling
    # -------------------------------------------------------------

    if default_limit < 1:
        return ValidationResult(
            is_valid=False,
            errors=["default_limit must be greater than zero."],
        )

    sanitized = parsed
    has_limit = parsed.find(exp.Limit) is not None
    is_aggregate_only = _is_aggregate_only_query(parsed)

    # Apply the safety limit to top-level SELECT and UNION results.
    limitable = isinstance(parsed, (exp.Select, exp.Union))
    if not has_limit and limitable and not is_aggregate_only:
        sanitized = parsed.limit(default_limit)
        warnings.append(
            "No LIMIT clause found — automatically limited to "
            f"{default_limit} rows."
        )

    # -------------------------------------------------------------
    # Final SQL generation
    # -------------------------------------------------------------

    final_sql = sanitized.sql(
        dialect=parser_dialect,
    )

    logger.info(
        "SQL validated successfully | tables=%s | warnings=%s",
        sorted(referenced_tables),
        warnings,
    )

    return ValidationResult(
        is_valid=True,
        sanitized_sql=final_sql,
        errors=errors,
        warnings=warnings,
    )