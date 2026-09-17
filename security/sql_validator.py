"""
security/sql_validator.py
--------------------------
Defense-in-depth validation of LLM-generated SQL, BEFORE it is ever
executed against the database.

The application must never trust that the LLM followed the security
instructions in its prompt. Every generated query passes through this
validator regardless of how it was produced.

Layers implemented here:
  1. Single-statement check (no ';' stacked statements)
  2. Parseable-SQL check (via sqlglot)
  3. Statement-type allow-list (SELECT / WITH...SELECT only)
  4. Keyword/function deny-list (defense in depth even if the parser
     misses something)
  5. Table allow-list check (only tables that exist in the discovered
     schema, or an explicit allow-list, may be referenced)
  6. Automatic LIMIT injection when missing
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

import sqlglot
from sqlglot import exp

from utils.logging_config import get_logger

logger = get_logger(__name__)

# Statement types we will ever allow to reach the database.
_ALLOWED_ROOT_EXPRESSIONS = (exp.Select, exp.With, exp.Union)

# Hard deny-list of keywords that should never appear, even inside a
# SELECT (e.g. subqueries attempting DDL/DML via odd dialect quirks,
# or dangerous administrative functions).
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


def _extract_table_names(parsed: exp.Expression) -> Set[str]:
    return {
        table.name.lower()
        for table in parsed.find_all(exp.Table)
        if table.name
    }


def _extract_qualified_table_names(parsed: exp.Expression) -> Set[str]:
    """
    Like _extract_table_names, but preserves any schema/database
    qualifier (e.g. 'information_schema.tables'), which sqlglot's
    Table.name property strips off. Used for the system-table check
    since 'tables' alone is too ambiguous to block outright.
    """
    names: Set[str] = set()
    for table in parsed.find_all(exp.Table):
        if not table.name:
            continue
        db = table.args.get("db")
        if db:
            names.add(f"{db.name}.{table.name}".lower())
        else:
            names.add(table.name.lower())
    return names


def _has_multiple_statements(sql: str) -> bool:
    # A single trailing semicolon is fine; anything else with a ';'
    # followed by more non-whitespace content means stacked statements.
    stripped = sql.strip().rstrip(";")
    return ";" in stripped


def validate_sql(
    sql: str,
    allowed_tables: Optional[Set[str]] = None,
    dialect: str = "mysql",
    default_limit: int = _DEFAULT_LIMIT,
) -> ValidationResult:
    """
    Validate (and, where safe, auto-correct) a generated SQL string.

    allowed_tables: lower-cased set of table names discovered from the
    live schema (or an explicit allow-list). If None, the table-name
    check is skipped (not recommended in production).
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, errors=["Generated SQL is empty."])

    # --- Layer 1: reject stacked statements -------------------------
    if _has_multiple_statements(sql):
        return ValidationResult(
            is_valid=False,
            errors=["Multiple SQL statements are not allowed."],
        )

    # --- Layer 2: deny-list keyword scan (defense in depth) ----------
    if _DENIED_PATTERN.search(sql):
        return ValidationResult(
            is_valid=False,
            errors=["The query contains a disallowed keyword or function."],
        )

    # --- Layer 3: parse the SQL ---------------------------------------
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:  # sqlglot raises its own ParseError subclasses
        logger.warning("SQL failed to parse: %s", exc)
        return ValidationResult(
            is_valid=False, errors=[f"The generated SQL is not valid: {exc}"]
        )

    # --- Layer 4: statement-type allow-list ---------------------------
    if not isinstance(parsed, _ALLOWED_ROOT_EXPRESSIONS):
        return ValidationResult(
            is_valid=False,
            errors=["Only SELECT (or WITH ... SELECT) statements are permitted."],
        )

    # Reject any nested DML/DDL node the parser may have accepted inside
    # a CTE/subquery in a permissive dialect mode.
    forbidden_node_types = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
        exp.Create, exp.Command,
    )
    if any(parsed.find(node_type) for node_type in forbidden_node_types):
        return ValidationResult(
            is_valid=False,
            errors=["The query contains a disallowed operation."],
        )

    # --- Layer 5: table allow-list -------------------------------------
    referenced_tables = _extract_table_names(parsed)
    qualified_tables = _extract_qualified_table_names(parsed)

    for table in qualified_tables:
        if any(table.startswith(prefix) for prefix in _SYSTEM_TABLE_PREFIXES):
            return ValidationResult(
                is_valid=False,
                errors=[f"Access to system table '{table}' is not allowed."],
            )

    if allowed_tables is not None:
        unknown = {t for t in referenced_tables if t not in allowed_tables}
        if unknown:
            return ValidationResult(
                is_valid=False,
                errors=[
                    "The query references tables that are not part of the "
                    f"known schema: {', '.join(sorted(unknown))}"
                ],
            )

    # --- Layer 6: enforce a LIMIT when missing --------------------------
    sanitized = parsed
    has_limit = parsed.find(exp.Limit) is not None
    is_aggregate_only = (
        isinstance(parsed, exp.Select)
        and parsed.find(exp.Group) is None
        and any(isinstance(e, (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min))
                for e in parsed.find_all(exp.AggFunc))
    )

    if not has_limit and isinstance(parsed, exp.Select) and not is_aggregate_only:
        sanitized = parsed.limit(default_limit)
        warnings.append(f"No LIMIT clause found — automatically limited to {default_limit} rows.")

    final_sql = sanitized.sql(dialect=dialect)

    logger.info(
        "SQL validated successfully | tables=%s | warnings=%s",
        sorted(referenced_tables), warnings,
    )

    return ValidationResult(
        is_valid=True, sanitized_sql=final_sql, errors=errors, warnings=warnings
    )
