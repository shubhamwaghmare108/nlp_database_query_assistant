"""
app.py
------
Streamlit UI for the NLP Database Query Assistant.

This module contains ONLY presentation logic. All business logic lives
in services/query_service.py — this file just wires user input to that
service and renders the response.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from auth.session import clear_user_session
from config import DatabaseSettings, settings
from database.connection import test_connection
from database.schema import get_database_schema
from services.query_service import QueryHistoryEntry, answer_question
from visualization.charts import build_chart, suggest_chart_type

st.set_page_config(
    page_title="NLP Database Query Assistant",
    page_icon="🗄️",
    layout="wide",
)

if "history" not in st.session_state:
    st.session_state.history: list[QueryHistoryEntry] = []
if "conversation" not in st.session_state:
    st.session_state.conversation: list[str] = []
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "configured_database_profile" not in st.session_state:
    st.session_state.configured_database_profile = None
if "app_view" not in st.session_state:
    st.session_state.app_view = "Query assistant"


def _database_profiles():
    """Return all choices, including compatibility with older app state."""
    profiles = dict(
        getattr(settings, "all_database_profiles", settings.database_profiles)
    )
    configured = st.session_state.get("configured_database_profile")
    if configured is not None:
        profiles["Session configuration"] = configured
    return profiles


def _database_type_options() -> dict[str, str]:
    return {
        "MySQL": "mysql",
        "MariaDB": "mariadb",
        "PostgreSQL": "postgresql",
        "SQLite": "sqlite",
        "SQL Server": "mssql",
        "Oracle": "oracle",
        "DuckDB": "duckdb",
        "Snowflake": "snowflake",
        "BigQuery": "bigquery",
    }


@st.cache_data(ttl=300, show_spinner=False)
def _cached_schema_text(profile_name: str) -> str:
    profile = _database_profiles()[profile_name]
    schema = get_database_schema(profile=profile)
    return schema.to_prompt_text()


def render_database_configuration() -> None:
    st.title("Database configuration")
    st.caption("Configure a connection for this browser session.")

    options = _database_type_options()
    current = st.session_state.get("configured_database_profile")
    default_dialect = current.dialect if current else settings.database.dialect
    dialect_names = list(options)
    default_name = next(
        (name for name, dialect in options.items() if dialect == default_dialect),
        dialect_names[0],
    )

    with st.form("database_configuration_form", clear_on_submit=False):
        database_name = st.selectbox(
            "RDBMS",
            dialect_names,
            index=dialect_names.index(default_name),
            help="The selected database type controls the SQL dialect and connection URL.",
        )
        dialect = options[database_name]

        if dialect in {"sqlite", "duckdb"}:
            database_path = st.text_input(
                "Database file path",
                value=(current.name if current and current.dialect == dialect else ""),
                placeholder="data/app.db",
            )
            host = "localhost"
            port = 0
            name = database_path
            user = ""
            password = ""
        else:
            default_host = current.host if current and current.dialect == dialect else "localhost"
            default_ports = {
                "mysql": 3306,
                "mariadb": 3306,
                "postgresql": 5432,
                "mssql": 1433,
                "oracle": 1521,
                "snowflake": 443,
                "bigquery": 443,
            }
            default_port = current.port if current and current.dialect == dialect else default_ports[dialect]
            default_name_value = current.name if current and current.dialect == dialect else ""
            default_user = current.user if current and current.dialect == dialect else ""
            default_password = current.password if current and current.dialect == dialect else ""

            host = st.text_input("Host or account", value=default_host)
            port = st.number_input("Port", min_value=0, max_value=65535, value=default_port)
            name = st.text_input("Database, service, project, or warehouse", value=default_name_value)
            user = st.text_input("Username", value=default_user)
            password = st.text_input("Password", value=default_password, type="password")

        save_col, test_col = st.columns(2)
        with save_col:
            save = st.form_submit_button("Save configuration", width="stretch")
        with test_col:
            test = st.form_submit_button("Test connection", width="stretch")

    if save or test:
        profile = DatabaseSettings(
            dialect=dialect,
            host=host,
            port=int(port),
            name=name,
            user=user,
            password=password,
        )
        if test:
            with st.spinner("Testing database connection..."):
                if test_connection(profile):
                    st.success("Connection successful.")
                else:
                    st.error("Connection failed. Check the RDBMS, host, port, and credentials.")
        if save:
            st.session_state.configured_database_profile = profile
            st.session_state.app_view = "Query assistant"
            st.toast("Database configuration saved for this session.", icon="✅", duration=3)
            st.rerun()

    if current:
        st.info(f"Active session configuration: {current.dialect.upper()} at {current.host}")


def render_sidebar() -> tuple[str, str]:
    with st.sidebar:
        st.header("NLP Query Assistant")
        view = st.radio(
            "View",
            ["Query assistant", "Database configuration"],
            key="app_view",
        )

        if st.button("Logout", key="logout_button", use_container_width=True):
            clear_user_session(st.session_state)
            st.cache_data.clear()
            st.rerun()

        if view == "Database configuration":
            return view, ""

        st.header("Database")
        profiles = _database_profiles()
        profile_name = st.selectbox(
            "Connection profile",
            list(profiles),
            key="database_profile",
        )
        profile = profiles[profile_name]
        connected = test_connection(profile)
        if connected:
            st.success(f"● Connected to `{profile.name or profile.dialect}`")
        else:
            st.error("● Not connected")
            st.caption("Check your .env database configuration.")

        with st.expander("Schema", expanded=False):
            if connected:
                try:
                    st.code(_cached_schema_text(profile_name), language="text")
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"Could not load schema: {exc}")
            else:
                st.caption("Connect to a database to view its schema.")

        st.divider()
        st.caption(f"LLM provider: **{settings.llm.provider}**")
        st.caption(f"Environment: **{settings.app.env}**")
    return view, profile_name


def render_query_form() -> str | None:
    st.subheader("Ask your question")
    with st.form("query_form", clear_on_submit=False):
        question = st.text_input(
            "Ask a question about your data...",
            placeholder="e.g. Show the top 5 customers by total sales",
            key="question_input",
        )
        generate_col, clear_col = st.columns([3, 1])
        with generate_col:
            submitted = st.form_submit_button("Generate Query", width="stretch")
        with clear_col:
            cleared = st.form_submit_button(
                "Clear",
                width="stretch",
                on_click=lambda: st.session_state.__setitem__("question_input", ""),
            )
    if cleared:
        return None
    return question if submitted else None


def render_response(response) -> None:
    if not response.success:
        st.error(response.error_message)
        if response.sql:
            with st.expander("Last attempted SQL"):
                st.code(response.sql, language="sql")
        return

    st.toast("Query executed successfully.", icon="✅", duration=3)

    for warning in response.warnings:
        st.info(warning)

    st.markdown("#### Generated SQL")
    st.code(response.sql, language="sql")

    st.markdown("#### Query Results")
    if response.dataframe.empty:
        st.warning("The query executed successfully but returned no results.")
    else:
        st.dataframe(response.dataframe, width="stretch")
        if response.truncated:
            st.caption(
                f"Showing the first {response.row_count} rows "
                f"(result was truncated for performance)."
            )

        st.markdown("#### Visualization")
        suggested = suggest_chart_type(response.dataframe)
        chart_options = ["Auto", "Bar", "Line", "Pie", "Scatter", "Table"]
        default_index = (
            chart_options.index(suggested.capitalize())
            if suggested and suggested.capitalize() in chart_options
            else 0
        )
        chosen = st.selectbox("Chart type", chart_options, index=default_index)

        chart_type = suggested if chosen == "Auto" else chosen.lower()
        if chart_type:
            fig = build_chart(response.dataframe, chart_type)
            if fig is not None:
                st.plotly_chart(fig, width="stretch")
            else:
                st.caption("The current data shape isn't suitable for this chart type.")
        else:
            st.caption("No suitable automatic chart for this result shape.")

    if response.explanation:
        st.markdown("#### AI Explanation")
        st.write(response.explanation)


def render_history() -> None:
    st.subheader("Query History")
    if not st.session_state.history:
        st.caption("No queries yet this session.")
        return

    rows = [
        {
            "Time": h.timestamp.strftime("%H:%M:%S"),
            "Question": h.question,
            "Status": "✅ Success" if h.status == "success" else "❌ Failed",
            "Rows": h.row_count,
            "Time (s)": h.execution_time_seconds,
        }
        for h in reversed(st.session_state.history)
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def main() -> None:
    st.title("🗄️ NLP Database Query Assistant")
    st.caption("Ask questions about your data in plain English — no SQL required.")

    view, selected_profile_name = render_sidebar()
    if view == "Database configuration":
        render_database_configuration()
        return

    selected_profile = _database_profiles()[selected_profile_name]

    question = render_query_form()

    if question is not None:
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Generating and executing your query..."):
                response = answer_question(
                    user_question=question,
                    conversation_history=st.session_state.conversation,
                    dialect=selected_profile.dialect,
                    database_profile=selected_profile,
                )

            st.session_state.last_response = response
            st.session_state.conversation.append(f"User: {question}")
            if response.success:
                st.session_state.conversation.append(f"SQL: {response.sql}")

            st.session_state.history.append(
                QueryHistoryEntry(
                    timestamp=datetime.now(),
                    question=question,
                    generated_sql=response.sql,
                    status="success" if response.success else "failed",
                    execution_time_seconds=0.0,
                    row_count=response.row_count,
                    error_message=response.error_message,
                )
            )

    if st.session_state.last_response is not None:
        st.divider()
        render_response(st.session_state.last_response)

    st.divider()
    render_history()


if __name__ == "__main__":
    main()
