"""Streamlit UI for the NLP Database Query Assistant."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from auth.session import clear_user_session
from config import DatabaseSettings, settings
from database.connection import test_connection
from database.schema import get_database_schema
from nlp.llm_client import LLMError, get_llm_client
from services.query_service import QueryHistoryEntry, answer_question
from visualization.charts import build_chart, suggest_chart_type

st.set_page_config(page_title="NLP Database Query Assistant", page_icon="🗄️", layout="wide")

st.session_state.setdefault("history", [])
st.session_state.setdefault("conversation", [])
st.session_state.setdefault("last_response", None)
st.session_state.setdefault("configured_database_profile", None)
st.session_state.setdefault("app_view", "Query assistant")
st.session_state.setdefault("show_logout", True)

_pending_view = st.session_state.pop("pending_app_view", None)
if _pending_view in {"Query assistant", "Database configuration"}:
    st.session_state["app_view"] = _pending_view


def _value(current, field: str, default=""):
    return getattr(current, field, default) if current is not None else default


def _database_profiles():
    profiles = dict(getattr(settings, "all_database_profiles", settings.database_profiles))
    configured = st.session_state.get("configured_database_profile")
    if configured is not None:
        profiles["Session configuration"] = configured
    return profiles


def _database_type_options() -> dict[str, str]:
    return {
        "MySQL": "mysql", "MariaDB": "mariadb", "PostgreSQL": "postgresql",
        "SQLite": "sqlite", "SQL Server": "mssql", "Oracle": "oracle",
        "DuckDB": "duckdb", "Snowflake": "snowflake", "BigQuery": "bigquery",
    }


@st.cache_data(ttl=300, show_spinner=False)
def _cached_schema_text(profile_name: str) -> str:
    return get_database_schema(profile=_database_profiles()[profile_name]).to_prompt_text()


def render_database_configuration() -> None:
    st.title("Database configuration")
    st.caption("Configure a database connection for this browser session.")
    options = _database_type_options()
    current = st.session_state.get("configured_database_profile")
    names = list(options)
    default = _value(current, "dialect", settings.database.dialect)
    default_name = next((name for name, dialect in options.items() if dialect == default), names[0])

    with st.form("database_configuration_form", clear_on_submit=False):
        database_name = st.selectbox("RDBMS", names, index=names.index(default_name))
        dialect = options[database_name]
        host, port, name, user, password = "localhost", 0, "", "", ""
        ssl_ca = ssl_cert = ssl_key = ssl_mode = ""
        authentication = "sql"
        warehouse = schema = role = project_id = dataset = credentials_file = ""
        read_only = False
        oracle_identifier = "service_name"

        if dialect in {"sqlite", "duckdb"}:
            name = st.text_input("Database file path", value=_value(current, "name"), placeholder="data/app.db")
            read_only = st.checkbox("Read-only mode", value=_value(current, "read_only", False))
        elif dialect in {"mysql", "mariadb"}:
            host = st.text_input("Host", value=_value(current, "host", "localhost"))
            port = st.number_input("Port", 0, 65535, int(_value(current, "port", 3306)))
            name = st.text_input("Database", value=_value(current, "name"))
            user = st.text_input("Username", value=_value(current, "user"))
            password = st.text_input("Password", value=_value(current, "password"), type="password")
            with st.expander("SSL options"):
                ssl_ca = st.text_input("CA certificate path", value=_value(current, "ssl_ca"))
                ssl_cert = st.text_input("Client certificate path", value=_value(current, "ssl_cert"))
                ssl_key = st.text_input("Client private key path", value=_value(current, "ssl_key"))
                ssl_mode = st.text_input("SSL mode", value=_value(current, "ssl_mode"))
        elif dialect == "postgresql":
            host = st.text_input("Host", value=_value(current, "host", "localhost"))
            port = st.number_input("Port", 0, 65535, int(_value(current, "port", 5432)))
            name = st.text_input("Database", value=_value(current, "name"))
            user = st.text_input("Username", value=_value(current, "user"))
            password = st.text_input("Password", value=_value(current, "password"), type="password")
            ssl_modes = ["", "disable", "prefer", "require", "verify-ca", "verify-full"]
            ssl_mode = st.selectbox("SSL mode", ssl_modes, index=ssl_modes.index(_value(current, "ssl_mode", "")))
            with st.expander("SSL certificate options"):
                ssl_ca = st.text_input("Root CA path", value=_value(current, "ssl_ca"))
                ssl_cert = st.text_input("Client certificate path", value=_value(current, "ssl_cert"))
                ssl_key = st.text_input("Client private key path", value=_value(current, "ssl_key"))
        elif dialect == "mssql":
            host = st.text_input("Server", value=_value(current, "host", "localhost"))
            port = st.number_input("Port", 0, 65535, int(_value(current, "port", 1433)))
            name = st.text_input("Database", value=_value(current, "name"))
            auth_modes = ["sql", "windows"]
            authentication = st.selectbox("Authentication mode", auth_modes, index=auth_modes.index(_value(current, "authentication", "sql")))
            if authentication == "sql":
                user = st.text_input("Username", value=_value(current, "user"))
                password = st.text_input("Password", value=_value(current, "password"), type="password")
        elif dialect == "oracle":
            host = st.text_input("Host", value=_value(current, "host", "localhost"))
            port = st.number_input("Port", 0, 65535, int(_value(current, "port", 1521)))
            identifier_modes = ["service_name", "sid"]
            oracle_identifier = st.selectbox("Identifier type", identifier_modes, index=identifier_modes.index(_value(current, "oracle_identifier", "service_name")))
            name = st.text_input("Service name or SID", value=_value(current, "name"))
            user = st.text_input("Username", value=_value(current, "user"))
            password = st.text_input("Password", value=_value(current, "password"), type="password")
        elif dialect == "snowflake":
            host = st.text_input("Account", value=_value(current, "host"))
            user = st.text_input("Username", value=_value(current, "user"))
            password = st.text_input("Password", value=_value(current, "password"), type="password")
            warehouse = st.text_input("Warehouse", value=_value(current, "warehouse"))
            name = st.text_input("Database", value=_value(current, "name"))
            schema = st.text_input("Schema", value=_value(current, "schema"))
            role = st.text_input("Role", value=_value(current, "role"))
        else:
            project_id = st.text_input("Project ID", value=_value(current, "project_id"))
            dataset = st.text_input("Dataset", value=_value(current, "dataset"))
            credentials_file = st.text_input("Credentials JSON path", value=_value(current, "credentials_file"))
            host, name, port = project_id, project_id, 443

        save, test = st.columns(2)
        with save:
            save_clicked = st.form_submit_button("Save configuration", width="stretch")
        with test:
            test_clicked = st.form_submit_button("Test connection", width="stretch")

    if not (save_clicked or test_clicked):
        return
    required = []
    if dialect in {"sqlite", "duckdb"} and not name.strip():
        required.append("database file path")
    elif dialect in {"mysql", "mariadb", "postgresql", "mssql", "oracle"} and not name.strip():
        required.append("database name")
    elif dialect == "snowflake" and (not host.strip() or not name.strip()):
        required.append("account and database")
    elif dialect == "bigquery" and (not project_id.strip() or not dataset.strip()):
        required.append("project ID and dataset")
    if required:
        st.error("Please provide: " + ", ".join(required) + ".")
        return

    profile = DatabaseSettings(
        dialect=dialect, host=host, port=int(port), name=name, user=user, password=password,
        ssl_ca=ssl_ca, ssl_cert=ssl_cert, ssl_key=ssl_key, ssl_mode=ssl_mode,
        authentication=authentication, warehouse=warehouse, schema=schema, role=role,
        project_id=project_id, dataset=dataset, credentials_file=credentials_file,
        read_only=read_only, oracle_identifier=oracle_identifier,
    )
    if test_clicked:
        with st.spinner("Testing database connection..."):
            if test_connection(profile):
                st.success("Connection successful.")
            else:
                st.error("Connection failed. Check the selected RDBMS and connection details.")
    if save_clicked:
        st.session_state.configured_database_profile = profile
        st.success("Database configuration saved for this session.")


def render_sidebar() -> tuple[str, str | None]:
    with st.sidebar:
        st.header("NLP Query Assistant")
        view = st.radio("View", ["Query assistant", "Database configuration"], key="app_view")

        if st.session_state.get("show_logout", True):
            if st.button("Logout", key="logout_button", use_container_width=True):
                clear_user_session(st.session_state)
                st.session_state["show_logout"] = False
                st.cache_data.clear()
                st.rerun()

        if view == "Database configuration":
            return view, None

        profiles = _database_profiles()
        if not profiles:
            st.info("No connection profiles are configured yet.")
            st.caption("Open Database configuration to create a session connection.")
            return view, None

        profile_name = st.selectbox("Connection profile", list(profiles), key="database_profile")
        profile = profiles[profile_name]
        connected = test_connection(profile)
        if connected:
            st.success(f"● Connected to `{profile.name or profile.dialect}`")
        else:
            st.error("● Not connected")
        with st.expander("Schema"):
            if connected:
                try:
                    st.code(_cached_schema_text(profile_name), language="text")
                except Exception as exc:
                    st.warning(f"Could not load schema: {exc}")
            else:
                st.caption("Connect to a database to view its schema.")
        st.caption(f"LLM provider: **{settings.llm.provider}**")
        st.caption(f"Environment: **{settings.app.env}**")
    return view, profile_name


def render_query_form() -> str | None:
    """Render a native Streamlit microphone recorder and the query form."""
    audio = st.audio_input("🎙️ Dictate your database question", key="dictation_audio")
    if audio is not None:
        audio_bytes = audio.getvalue()
        if audio_bytes:
            audio_signature = hash(audio_bytes)
            if st.session_state.get("transcribed_audio_signature") != audio_signature:
                with st.spinner("Transcribing your question..."):
                    try:
                        transcript = get_llm_client().transcribe_audio(
                            audio_bytes,
                            mime_type=getattr(audio, "type", None) or "audio/wav",
                        )
                        st.session_state["question_input"] = transcript
                        st.session_state["transcribed_audio_signature"] = audio_signature
                        st.success("Speech recognized. You can edit the question before submitting.")
                    except LLMError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Could not transcribe audio: {exc}")

    with st.form("query_form", clear_on_submit=False):
        question = st.text_input(
            "Ask a question about your data...",
            placeholder="e.g. Show the top 5 customers by total sales",
            key="question_input",
        )
        submitted = st.form_submit_button("Generate Query", width="stretch")
    return question if submitted else None


def render_response(response) -> None:
    if not response.success:
        st.error(response.error_message)
        if response.sql:
            st.code(response.sql, language="sql")
        return
    st.code(response.sql, language="sql")
    if response.dataframe.empty:
        st.warning("The query returned no results.")
    else:
        st.dataframe(response.dataframe, width="stretch")
        chart_type = st.selectbox("Chart type", ["Auto", "Bar", "Line", "Pie", "Scatter", "Table"])
        chosen = suggest_chart_type(response.dataframe) if chart_type == "Auto" else chart_type.lower()
        if chosen:
            figure = build_chart(response.dataframe, chosen)
            if figure is not None:
                st.plotly_chart(figure, width="stretch")
    if response.explanation:
        st.write(response.explanation)


def main() -> None:
    st.title("🗄️ NLP Database Query Assistant")
    st.caption("Ask questions about your data in plain English — no SQL required.")
    view, profile_name = render_sidebar()
    if view == "Database configuration":
        render_database_configuration()
        return
    if profile_name is None:
        st.warning("No database connection is available. Configure a connection before using the query assistant.")
        render_database_configuration()
        return

    profile = _database_profiles()[profile_name]
    question = render_query_form()
    if question is not None:
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Generating and executing your query..."):
                response = answer_question(
                    user_question=question,
                    conversation_history=st.session_state.conversation,
                    dialect=profile.dialect,
                    database_profile=profile,
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
        render_response(st.session_state.last_response)


if __name__ == "__main__":
    main()
