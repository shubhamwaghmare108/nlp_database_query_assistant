"""database/schema.py
-------------------
Dynamic database schema discovery. Nothing about the schema is
hard-coded anywhere in the application — it is always read live from
the database via SQLAlchemy's Inspector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from config import DatabaseSettings, settings
from database.connection import get_engine
from utils.logging_config import get_logger

logger = get_logger(__name__)

_SYSTEM_SCHEMAS = {
    "information_schema",
    "performance_schema",
    "mysql",
    "sys",
    "pg_catalog",
    "public_information_schema",
}


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_primary_key: bool = False
    is_nullable: bool = True


@dataclass
class ForeignKeyInfo:
    constrained_columns: List[str]
    referred_table: str
    referred_columns: List[str]


@dataclass
class TableInfo:
    name: str
    columns: List[ColumnInfo] = field(default_factory=list)
    foreign_keys: List[ForeignKeyInfo] = field(default_factory=list)


@dataclass
class DatabaseSchema:
    database_name: str
    tables: Dict[str, TableInfo] = field(default_factory=dict)

    def table_names(self) -> List[str]:
        return list(self.tables.keys())

    def to_prompt_text(self, only_tables: Optional[List[str]] = None) -> str:
        lines: List[str] = [f"Database: {self.database_name}", ""]
        table_iter = (
            [t for t in self.tables.values() if t.name in only_tables]
            if only_tables
            else list(self.tables.values())
        )
        for table in table_iter:
            lines.append(f"Table: {table.name}")
            lines.append("-" * 40)
            pk_names = {c.name for c in table.columns if c.is_primary_key}
            for col in table.columns:
                marker = " PRIMARY KEY" if col.name in pk_names else ""
                lines.append(f"{col.name:<20} {col.data_type}{marker}")
            for fk in table.foreign_keys:
                lines.append(
                    f"FOREIGN KEY ({', '.join(fk.constrained_columns)}) "
                    f"REFERENCES {fk.referred_table}({', '.join(fk.referred_columns)})"
                )
            lines.append("")
        return "\n".join(lines)


def _inspection_schema(profile: DatabaseSettings) -> Optional[str]:
    """Return the SQLAlchemy Inspector schema/dataset to inspect."""
    if profile.schema:
        return profile.schema
    if profile.dialect in {"bigquery", "googlebigquery"} and profile.dataset:
        return profile.dataset
    return None


def _supports_explicit_schema(profile: DatabaseSettings) -> bool:
    return profile.dialect in {
        "postgres",
        "postgresql",
        "mssql",
        "sqlserver",
        "oracle",
        "snowflake",
        "bigquery",
        "googlebigquery",
        "duckdb",
        "sqlite",
    }


def get_database_schema(
    engine: Optional[Engine] = None,
    profile: Optional[DatabaseSettings] = None,
) -> DatabaseSchema:
    """
    Inspect the live database and build a DatabaseSchema object.
    This should be cached by the caller (e.g. Streamlit's st.cache_data)
    since schema rarely changes within a session.
    """
    db_settings = profile or settings.database
    engine = engine or get_engine(profile)
    inspector = inspect(engine)

    db_name = engine.url.database or "unknown"
    inspection_schema = _inspection_schema(db_settings)
    inspector_schema = (
        inspection_schema if _supports_explicit_schema(db_settings) else None
    )

    if inspection_schema and inspection_schema.lower() in _SYSTEM_SCHEMAS:
        logger.warning("Refusing to expose system schema: %s", inspection_schema)
        return DatabaseSchema(database_name=db_name)

    schema = DatabaseSchema(database_name=db_name)
    inspection_kwargs = {"schema": inspector_schema} if inspector_schema else {}

    table_names = inspector.get_table_names(**inspection_kwargs)
    for table_name in table_names:
        if table_name.lower() in _SYSTEM_SCHEMAS:
            continue

        pk_constraint = inspector.get_pk_constraint(table_name, **inspection_kwargs)
        pk_columns = set(pk_constraint.get("constrained_columns") or [])

        columns = [
            ColumnInfo(
                name=col["name"],
                data_type=str(col["type"]),
                is_primary_key=col["name"] in pk_columns,
                is_nullable=col.get("nullable", True),
            )
            for col in inspector.get_columns(table_name, **inspection_kwargs)
        ]

        foreign_keys = [
            ForeignKeyInfo(
                constrained_columns=fk["constrained_columns"],
                referred_table=fk["referred_table"],
                referred_columns=fk["referred_columns"],
            )
            for fk in inspector.get_foreign_keys(table_name, **inspection_kwargs)
        ]

        schema.tables[table_name] = TableInfo(
            name=table_name, columns=columns, foreign_keys=foreign_keys
        )

    logger.info(
        "Discovered schema: %d tables in %s%s",
        len(schema.tables),
        db_name,
        f" (schema={inspection_schema})" if inspection_schema else "",
    )
    return schema
