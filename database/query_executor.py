"""
database/query_executor.py
---------------------------
Executes validated, read-only SQL against the database and returns
results as a pandas DataFrame. This module assumes the SQL it
receives has ALREADY passed security.sql_validator — it does not
re-validate, but it does enforce execution-level protections
(timeout, row limits) as a second line of defense.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from database.connection import get_engine
from utils.helpers import timer
from utils.logging_config import get_logger

logger = get_logger(__name__)


class QueryExecutionError(Exception):
    """Raised when a query fails to execute against the database."""


@dataclass
class QueryExecutionResult:
    dataframe: pd.DataFrame
    row_count: int
    execution_time_seconds: float
    truncated: bool


def execute_select_query(
    sql: str, max_rows: Optional[int] = None
) -> QueryExecutionResult:
    """
    Execute a SELECT (read-only) query and return results as a DataFrame.

    - Uses a connection from the pooled engine.
    - Enforces MAX_RESULT_ROWS by fetching max_rows + 1 and trimming, so
      we can tell the user results were truncated.
    - Wraps SQLAlchemy exceptions in QueryExecutionError with a
      user-safe message (no credentials/stack traces leaked upward).
    """
    max_rows = max_rows or settings.app.max_result_rows
    engine = get_engine()

    try:
        with timer() as t:
            with engine.connect() as conn:
                # execution_options(stream_results=True) lets us cap
                # memory use on very large result sets.
                result_proxy = conn.execution_options(
                    stream_results=True
                ).execute(text(sql))
                columns = list(result_proxy.keys())
                rows = result_proxy.fetchmany(max_rows + 1)

        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        df = pd.DataFrame(rows, columns=columns)

        logger.info(
            "Query executed successfully | rows=%d | truncated=%s | time=%.3fs",
            len(df),
            truncated,
            t["elapsed"],
        )

        return QueryExecutionResult(
            dataframe=df,
            row_count=len(df),
            execution_time_seconds=t["elapsed"],
            truncated=truncated,
        )

    except SQLAlchemyError as exc:
        logger.error("Query execution failed: %s", exc)
        raise QueryExecutionError(
            "The query could not be executed against the database. "
            "Please rephrase your question or check the data referenced."
        ) from exc
