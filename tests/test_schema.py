import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import DatabaseSettings  # noqa: E402
from database import schema as schema_module  # noqa: E402


class FakeInspector:
    def __init__(self):
        self.calls = []

    def get_table_names(self, **kwargs):
        self.calls.append(("tables", kwargs))
        return ["customers"]

    def get_pk_constraint(self, table_name, **kwargs):
        self.calls.append(("pk", table_name, kwargs))
        return {"constrained_columns": ["id"]}

    def get_columns(self, table_name, **kwargs):
        self.calls.append(("columns", table_name, kwargs))
        return [{"name": "id", "type": "INTEGER", "nullable": False}]

    def get_foreign_keys(self, table_name, **kwargs):
        self.calls.append(("fks", table_name, kwargs))
        return []


def test_configured_postgres_schema_is_used_for_inspection(monkeypatch):
    inspector = FakeInspector()
    monkeypatch.setattr(schema_module, "inspect", lambda engine: inspector)

    engine = SimpleNamespace(url=SimpleNamespace(database="sales"))
    profile = DatabaseSettings(
        dialect="postgresql",
        host="db.example.com",
        name="sales",
        schema="analytics",
    )

    result = schema_module.get_database_schema(engine=engine, profile=profile)

    assert result.table_names() == ["customers"]
    assert inspector.calls[0] == ("tables", {"schema": "analytics"})
    assert all(
        call[-1] == {"schema": "analytics"}
        for call in inspector.calls
    )


def test_bigquery_dataset_is_used_when_schema_is_not_set(monkeypatch):
    inspector = FakeInspector()
    monkeypatch.setattr(schema_module, "inspect", lambda engine: inspector)

    engine = SimpleNamespace(url=SimpleNamespace(database="project"))
    profile = DatabaseSettings(
        dialect="bigquery",
        project_id="project",
        dataset="analytics",
    )

    schema_module.get_database_schema(engine=engine, profile=profile)

    assert inspector.calls[0] == ("tables", {"schema": "analytics"})


def test_system_schema_is_not_exposed(monkeypatch):
    inspector = FakeInspector()
    monkeypatch.setattr(schema_module, "inspect", lambda engine: inspector)

    engine = SimpleNamespace(url=SimpleNamespace(database="sales"))
    profile = DatabaseSettings(
        dialect="postgresql",
        host="db.example.com",
        name="sales",
        schema="pg_catalog",
    )

    result = schema_module.get_database_schema(engine=engine, profile=profile)

    assert result.table_names() == []
    assert inspector.calls == []
