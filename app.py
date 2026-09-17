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

from config import settings
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


@st.cache_data(ttl=300, show_spinner=False)
def _cached_schema_text() -> str:
    schema = get_database_schema()
    return schema.to_prompt_text()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Database")
        connected = test_connection()
        if connected:
            st.success(f"● Connected to `{settings.database.name}`")
        else:
            st.error("● Not connected")
            st.caption("Check your .env database configuration.")

        with st.expander("Schema", expanded=False):
            if connected:
                try:
                    st.code(_cached_schema_text(), language="text")
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"Could not load schema: {exc}")
            else:
                st.caption("Connect to a database to view its schema.")

        st.divider()
        st.caption(f"LLM provider: **{settings.llm.provider}**")
        st.caption(f"Environment: **{settings.app.env}**")


def render_query_form() -> str | None:
    st.subheader("Ask your question")
    with st.form("query_form", clear_on_submit=False):
        question = st.text_input(
            "Ask a question about your data...",
            placeholder="e.g. Show the top 5 customers by total sales",
        )
        submitted = st.form_submit_button("Generate Query", use_container_width=True)
    return question if submitted else None


def render_response(response) -> None:
    if not response.success:
        st.error(response.error_message)
        if response.sql:
            with st.expander("Last attempted SQL"):
                st.code(response.sql, language="sql")
        return

    st.success("Query executed successfully.")

    for warning in response.warnings:
        st.info(warning)

    st.markdown("#### Generated SQL")
    st.code(response.sql, language="sql")

    st.markdown("#### Query Results")
    if response.dataframe.empty:
        st.warning("The query executed successfully but returned no results.")
    else:
        st.dataframe(response.dataframe, use_container_width=True)
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
                st.plotly_chart(fig, use_container_width=True)
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
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def main() -> None:
    st.title("🗄️ NLP Database Query Assistant")
    st.caption("Ask questions about your data in plain English — no SQL required.")

    render_sidebar()

    question = render_query_form()

    if question is not None:
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Generating and executing your query..."):
                response = answer_question(
                    user_question=question,
                    conversation_history=st.session_state.conversation,
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
