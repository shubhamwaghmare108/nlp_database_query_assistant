"""
services/query_service.py
--------------------------
Single orchestration point for the natural-language database query pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import List, Optional

import pandas as pd

from config import DatabaseSettings, settings
from database.query_executor import QueryExecutionError, execute_select_query
from database.schema import DatabaseSchema, get_database_schema
from nlp.llm_client import LLMError, get_llm_client
from nlp.prompt_builder import build_explanation_prompt
from nlp.sql_generator import SQLGenerationError, correct_sql, generate_sql
from security.sql_validator import validate_sql
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class QueryHistoryEntry:
    timestamp: datetime
    question: str
    generated_sql: Optional[str]
    status: str
    execution_time_seconds: float
    row_count: int
    error_message: Optional[str] = None


@dataclass
class QueryResponse:
    success: bool
    question: str
    sql: Optional[str] = None
    dataframe: Optional[pd.DataFrame] = None
    row_count: int = 0
    truncated: bool = False
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    explanation: Optional[str] = None


def _allowed_table_set(schema: DatabaseSchema) -> set[str]:
    if settings.app.allowed_tables:
        return {table.lower() for table in settings.app.allowed_tables}
    return {table.lower() for table in schema.table_names()}


def _clean_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _find_table(schema: DatabaseSchema, requested_name: str):
    """Find a table by exact name, case-insensitive name, or singular/plural form."""
    requested = _clean_identifier(requested_name)
    for table in schema.tables.values():
        candidate = _clean_identifier(table.name)
        if candidate == requested:
            return table
        if candidate.rstrip("s") == requested.rstrip("s"):
            return table
    return None


def _schema_metadata_response(
    question: str, schema: DatabaseSchema
) -> Optional[QueryResponse]:
    """Answer schema/introspection questions directly, without the LLM."""
    normalized = re.sub(r"[^a-z0-9_]+", " ", question.lower()).strip()
    if not re.search(r"\b(table|tables|relation|relations|schema|column|columns)\b", normalized):
        return None

    asks_for_names = any(
        phrase in normalized
        for phrase in (
            "name of table", "names of table", "list table", "list of table",
            "show table", "what table", "which table", "table names",
            "tables are there",
        )
    )
    asks_for_count = any(
        phrase in normalized
        for phrase in (
            "how many", "number of", "count of", "total number", "total tables",
        )
    )

    if asks_for_names:
        names = list(schema.table_names())
        dataframe = pd.DataFrame({"table_name": names})
        return QueryResponse(
            success=True,
            question=question,
            sql="-- Answered from discovered database schema: table names",
            dataframe=dataframe,
            row_count=len(dataframe),
            explanation=f"The connected database contains {len(names)} table(s).",
        )

    if asks_for_count:
        count = len(schema.table_names())
        return QueryResponse(
            success=True,
            question=question,
            sql="-- Answered from discovered database schema: table count",
            dataframe=pd.DataFrame({"table_count": [count]}),
            row_count=1,
            explanation=f"The connected database contains {count} table(s).",
        )

    describe_match = re.search(
        r"(?:describe|explain|structure|schema|columns?\s+of|details?\s+of)\s+(?:the\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:table)?",
        normalized,
    )
    if describe_match:
        requested_name = describe_match.group(1)
        table = _find_table(schema, requested_name)
        if table is None:
            return QueryResponse(
                success=False,
                question=question,
                error_message=(
                    f"Table '{requested_name}' was not found in the discovered schema. "
                    f"Available tables: {', '.join(schema.table_names()) or 'none'}"
                ),
            )

        rows = [
            {
                "column_name": column.name,
                "data_type": column.data_type,
                "is_primary_key": column.is_primary_key,
                "is_nullable": column.is_nullable,
            }
            for column in table.columns
        ]
        return QueryResponse(
            success=True,
            question=question,
            sql=f"-- Answered from discovered database schema: describe {table.name}",
            dataframe=pd.DataFrame(rows),
            row_count=len(rows),
            explanation=(
                f"Table '{table.name}' has {len(rows)} column(s). "
                "The result includes column names, data types, primary-key status, and nullability."
            ),
        )

    return None


def answer_question(
    user_question: str,
    conversation_history: Optional[List[str]] = None,
    dialect: str = "mysql",
    database_profile: Optional[DatabaseSettings] = None,
    generate_explanation: bool = True,
) -> QueryResponse:
    user_question = (user_question or "").strip()
    if not user_question:
        return QueryResponse(success=False, question=user_question, error_message="Please enter a question.")

    try:
        schema = (
            get_database_schema()
            if database_profile is None
            else get_database_schema(profile=database_profile)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Schema retrieval failed: %s", exc)
        return QueryResponse(
            success=False,
            question=user_question,
            error_message="Unable to connect to the database. Please check the database configuration.",
        )

    metadata_response = _schema_metadata_response(user_question, schema)
    if metadata_response is not None:
        return metadata_response

    allowed_tables = _allowed_table_set(schema)

    try:
        sql = generate_sql(
            schema=schema,
            user_question=user_question,
            dialect=dialect,
            conversation_history=conversation_history,
        )
    except SQLGenerationError as exc:
        return QueryResponse(success=False, question=user_question, error_message=str(exc))

    max_attempts = settings.app.max_sql_correction_attempts
    last_error = ""
    attempt = 0

    while attempt <= max_attempts:
        validation = validate_sql(sql, allowed_tables=allowed_tables, dialect=dialect)

        if not validation.is_valid:
            last_error = "; ".join(validation.errors)
            logger.warning("SQL failed validation (attempt %d): %s", attempt, last_error)
        else:
            sanitized_sql = validation.sanitized_sql
            if sanitized_sql is None:
                last_error = "SQL validation returned no executable query."
                break
            try:
                exec_result = (
                    execute_select_query(sanitized_sql)
                    if database_profile is None
                    else execute_select_query(sanitized_sql, profile=database_profile)
                )
                explanation = None
                if generate_explanation and not exec_result.dataframe.empty:
                    explanation = _generate_explanation(
                        user_question,
                        sanitized_sql,
                        exec_result.dataframe,
                        exec_result.row_count,
                    )
                return QueryResponse(
                    success=True,
                    question=user_question,
                    sql=sanitized_sql,
                    dataframe=exec_result.dataframe,
                    row_count=exec_result.row_count,
                    truncated=exec_result.truncated,
                    warnings=validation.warnings,
                    explanation=explanation,
                )
            except QueryExecutionError as exc:
                last_error = str(exc)
                logger.warning("SQL execution failed (attempt %d): %s", attempt, last_error)

        if attempt >= max_attempts:
            break

        try:
            sql = correct_sql(
                schema=schema,
                user_question=user_question,
                failed_sql=sql,
                error_message=last_error,
                dialect=dialect,
            )
        except SQLGenerationError as exc:
            last_error = str(exc)
            break
        attempt += 1

    return QueryResponse(
        success=False,
        question=user_question,
        sql=sql,
        error_message=(
            "The generated query failed security validation or execution "
            f"after {max_attempts + 1} attempt(s). Last error: {last_error}"
        ),
    )


def _generate_explanation(
    question: str, sql: str, df: pd.DataFrame, row_count: int
) -> Optional[str]:
    """Best-effort explanation generation; never blocks the main result."""
    try:
        preview = df.head(20).to_csv(index=False)
        system_instruction, prompt = build_explanation_prompt(
            user_question=question,
            sql=sql,
            result_preview_csv=preview,
            row_count=row_count,
        )
        client = get_llm_client()
        return client.generate(prompt, system_instruction=system_instruction)
    except LLMError as exc:
        logger.warning("Explanation generation failed (non-fatal): %s", exc)
        return None
