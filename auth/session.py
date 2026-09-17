"""Session helpers for the first single-user platform workflow.

The initial platform keeps connection details only in Streamlit session state.
This module centralizes cleanup so logout cannot accidentally leave credentials,
query history, schema cache keys, or generated results behind.
"""

from __future__ import annotations

from typing import Any


SESSION_KEYS_TO_CLEAR = (
    "configured_database_profile",
    "database_profile",
    "history",
    "conversation",
    "last_response",
    "question_input",
    "is_authenticated",
    "logged_in",
    "authenticated",
    "user",
)


def clear_user_session(session_state: Any) -> None:
    """Remove all platform-owned state from a Streamlit session.

    ``session_state`` is intentionally duck-typed so this helper can be tested
    with a plain dictionary without importing Streamlit.
    """
    for key in SESSION_KEYS_TO_CLEAR:
        try:
            del session_state[key]
        except (KeyError, AttributeError):
            continue

    # A fresh default view is safer than leaving the user on a stale query page.
    try:
        session_state["app_view"] = "Database configuration"
    except TypeError:
        setattr(session_state, "app_view", "Database configuration")
