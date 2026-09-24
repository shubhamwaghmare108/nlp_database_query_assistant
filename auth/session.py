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
    "dictation_audio",
    "transcribed_audio_signature",
)


def clear_user_session(session_state: Any) -> None:
    """Remove platform-owned state and hide the logout control."""
    for key in SESSION_KEYS_TO_CLEAR:
        try:
            del session_state[key]
        except (KeyError, AttributeError):
            continue

    # These flags are intentionally preserved across the logout-triggered
    # rerun. Otherwise app.py would restore the default and show Logout again.
    try:
        session_state["show_logout"] = False
        session_state["logged_out"] = True
    except TypeError:
        setattr(session_state, "show_logout", False)
        setattr(session_state, "logged_out", True)
