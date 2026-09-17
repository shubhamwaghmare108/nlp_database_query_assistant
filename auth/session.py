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
    """Remove platform-owned state and mark the session as logged out."""
    for key in SESSION_KEYS_TO_CLEAR:
        try:
            del session_state[key]
        except (KeyError, AttributeError):
            continue

    # Preserve this flag across the logout-triggered rerun so the Logout
    # button does not immediately reappear.
    try:
        session_state["logged_out"] = True
    except TypeError:
        setattr(session_state, "logged_out", True)
