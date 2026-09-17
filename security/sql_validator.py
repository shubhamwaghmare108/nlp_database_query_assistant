"""
security/sql_validator.py
--------------------------
Defense-in-depth validation of LLM-generated SQL, BEFORE it is ever
executed against the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

import sqlglot
from sqlglot import exp

from utils.logging_config import get_logger

logger = get_logger(__name__)

_ALLOWED_ROOT_EXPRESSIONS = (exp.Select, exp.With, exp.Union)
_DENIED_KEYWORDS = [
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b",
    r"\bALTER\b", r"\bTRUNCATE\b", r"\bCREATE\b", r"\bGRANT\b",
    r"\bREVOKE\b", r"\bEXEC\b", r"\bEXECUTE\b", r"\bCALL\b",
    r"\bMERGE\b", r"\bREPLACE\b", r"\bLOAD_FILE\b", r"\bINTO\s+OUTFILE\b",
    r"\bINTO\s+DUMPFILE\b", r"\bSLEEP\s*\(", r"\bBENCHMARK\s*\(",
    r"\bxp_cmdshell\b", r"\bATTACH\b", r"\bDETACH\b", r"\bPRAGMA\b",
]
_DENIED_PATTERN = re.compile("|".join(_DENIED_KEYWORDS), re.IGNORECASE)
_SYSTEM_TABLE_PREFIXES = (
    "information_schema", "performance_schema", "mysql.", "sys.", "pg_",
)
_DEFAULT_LIMIT = 500


@dataclass
class ValidationResult:
    is_valid: bool
    sanitized_sql: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _parser_dialect(dialect: str) -> str:
    """Return the sqlglot dialect name for an application RDBMS name."""
    normalized = (dialect or "mysql").strip().lower()
    # sqlglot parses MariaDB SQL using its MySQL dialect.
    return "mysql" if normalized == "mariadb" else normalized


def _extract_table_names(parsed: exp.Expression) -> Set[str]:
    return {table.name.lower() for table in parsed.find_all(exp.Table) if table.name}


def _extract_qualified_table_names(parsed: exp.Expression) -> Set[str]:
    names: Set[str] = set()
    for table in parsed.find_all(exp.Table):
        if not table.name:
            continue
        db = table.args.get("db")
        names.add(f"{db.name}.{table.name}".lower() if db else table.name.lower())
    return names


def _has_multiple_statements(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    return ";" in stripped


def validate_sql(
    sql: str,
    allowed_tables: Optional[Set[str]] = None,
    dialect: str = "mysql",
    default_limit: int = _DEFAULT_LIMIT,
) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, errors=["Generated SQL is empty."])
    if _has_multiple_statements(sql):
        return ValidationResult(is_valid=False, errors=["Multiple SQL statements are not allowed."])
    if _DENIED_PATTERN.search(sql):
        return ValidationResult(is_valid=False, errors=["The query contains a disallowed keyword or function."])

    parser_dialect = _parser_dialect(dialect)
    try:
        parsed = sqlglot.parse_one(sql, read=parser_dialect)
    except Exception as exc:
        logger.warning("SQL failed to parse: %s", exc)
        return ValidationResult(is_valid=False, errors=[f"The generated SQL is not valid: {exc}"])

    if not isinstance(parsed, _ALLOWED_ROOT_EXPRESSIONS):
        return ValidationResult(is_valid=False, errors=["Only SELECT (or WITH ... SELECT) statements are permitted."])

    forbidden_node_types = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create, exp.Command)
    if any(parsed.find(node_type) for node_type in forbidden_node_types):
        return ValidationResult(is_valid=False, errors=["The query contains a disallowed operation."])

    referenced_tables = _extract_table_names(parsed)
    qualified_tables = _extract_qualified_table_names(parsed)
    for table in qualified_tables:
        if any(table.startswith(prefix) for prefix in _SYSTEM_TABLE_PREFIXES):
            return ValidationResult(is_valid=False, errors=[f"Access to system table '{table}' is not allowed."])

    if allowed_tables is not None:
        unknown = {table for table in referenced_tables if table not in allowed_tables}
        if unknown:
            return ValidationResult(
                is_valid=False,
                errors=["The query references tables that are not part of the known schema: " + ", ".join(sorted(unknown))],
            )

    sanitized = parsed
    has_limit = parsed.find(exp.Limit) is not None
    is_aggregate_only = (
        isinstance(parsed, exp.Select)
        and parsed.find(exp.Group) is None
        and any(isinstance(node, (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)) for node in parsed.find_all(exp.AggFunc))
    )
    if not has_limit and isinstance(parsed, exp.Select) and not is_aggregate_only:
        sanitized = parsed.limit(default_limit)
        warnings.append(f"No LIMIT clause found — automatically limited to {default_limit} rows.")

    final_sql = sanitized.sql(dialect=parser_dialect)
    logger.info("SQL validated successfully | tables=%s | warnings=%s", sorted(referenced_tables), warnings)
    return ValidationResult(is_valid=True, sanitized_sql=final_sql, errors=errors, warnings=warnings)
