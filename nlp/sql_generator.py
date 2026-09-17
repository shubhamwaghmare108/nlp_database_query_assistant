"""
nlp/sql_generator.py
---------------------
Orchestrates turning a natural-language question into SQL text using
the configured LLM client. Also implements a lightweight schema
relevance filter so we don't send the entire database schema to the
LLM on every call.

This module does NOT validate or execute SQL — see security/sql_validator.py
and database/query_executor.py. Its only job is text-to-SQL generation.
"""

from __future__ import annotations

import re
from typing import List, Optional

from database.schema import DatabaseSchema
from nlp.llm_client import LLMError, get_llm_client
from nlp.prompt_builder import build_correction_prompt, build_schema_prompt
from utils.helpers import strip_markdown_fences, truncate_text
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SQLGenerationError(Exception):
    """Raised when the LLM cannot produce a usable SQL query."""


def select_relevant_tables(
    schema: DatabaseSchema, user_question: str, max_tables: int = 6
) -> List[str]:
    """
    Cheap, dependency-free relevance heuristic: score each table by how
    many of its name/column tokens appear in the question, then keep the
    top N (plus any table connected to a kept table via a foreign key,
    so joins remain possible). This keeps prompt size down for large
    schemas without requiring an extra LLM call.

    Falls back to "all tables" if nothing scores above zero (better to
    over-include than to silently drop a needed table).
    """
    question_tokens = set(re.findall(r"[a-zA-Z]+", user_question.lower()))

    scores: dict[str, int] = {}
    for table in schema.tables.values():
        tokens = {table.name.lower()}
        tokens.update(re.findall(r"[a-zA-Z]+", table.name.lower()))
        for col in table.columns:
            tokens.update(re.findall(r"[a-zA-Z]+", col.name.lower()))
        score = len(tokens & question_tokens)
        if score:
            scores[table.name] = score

    if not scores:
        return schema.table_names()

    ranked = sorted(scores, key=scores.get, reverse=True)[:max_tables]
    selected = set(ranked)

    # Pull in directly related tables so joins implied by the question
    # (e.g. "customers" -> "orders") remain answerable.
    for name in list(selected):
        table = schema.tables.get(name)
        if not table:
            continue
        for fk in table.foreign_keys:
            selected.add(fk.referred_table)

    return [t for t in schema.table_names() if t in selected]


def generate_sql(
    schema: DatabaseSchema,
    user_question: str,
    dialect: str = "mysql",
    conversation_history: Optional[List[str]] = None,
    use_relevant_tables_only: bool = True,
) -> str:
    """
    Generate a raw SQL string (not yet validated) for the given question.
    Raises SQLGenerationError on any failure, including the model
    explicitly reporting the question is unanswerable from this schema.
    """
    relevant_tables = (
        select_relevant_tables(schema, user_question)
        if use_relevant_tables_only
        else None
    )
    schema_text = truncate_text(
        schema.to_prompt_text(only_tables=relevant_tables), max_chars=6000
    )

    system_instruction, prompt = build_schema_prompt(
        schema_text=schema_text,
        user_question=user_question,
        dialect=dialect.upper(),
        conversation_history=conversation_history,
    )

    try:
        client = get_llm_client()
        raw = client.generate(prompt, system_instruction=system_instruction)
    except LLMError as exc:
        logger.error("SQL generation failed: %s", exc)
        raise SQLGenerationError(
            "Unable to generate SQL at this time. Please try again."
        ) from exc

    sql = strip_markdown_fences(raw)

    if sql.strip().upper() == "UNANSWERABLE":
        raise SQLGenerationError(
            "This question cannot be answered using the available data schema."
        )

    logger.info("SQL generated for question: %r", user_question)
    return sql


def correct_sql(
    schema: DatabaseSchema,
    user_question: str,
    failed_sql: str,
    error_message: str,
    dialect: str = "mysql",
) -> str:
    """Ask the LLM to correct a SQL query that failed validation/execution."""
    schema_text = truncate_text(schema.to_prompt_text(), max_chars=6000)
    system_instruction, prompt = build_correction_prompt(
        schema_text=schema_text,
        user_question=user_question,
        failed_sql=failed_sql,
        error_message=error_message,
        dialect=dialect.upper(),
    )

    try:
        client = get_llm_client()
        raw = client.generate(prompt, system_instruction=system_instruction)
    except LLMError as exc:
        logger.error("SQL correction failed: %s", exc)
        raise SQLGenerationError(
            "Unable to correct the SQL query at this time."
        ) from exc

    sql = strip_markdown_fences(raw)
    if sql.strip().upper() == "UNANSWERABLE":
        raise SQLGenerationError(
            "This question cannot be answered using the available data schema."
        )

    logger.info("SQL corrected for question: %r", user_question)
    return sql
