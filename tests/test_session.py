from auth.session import clear_user_session


def test_clear_user_session_removes_platform_state():
    state = {
        "configured_database_profile": object(),
        "database_profile": "Session configuration",
        "history": ["query"],
        "conversation": ["conversation"],
        "last_response": object(),
        "question_input": "secret question",
        "app_view": "Query assistant",
        "unrelated": "keep",
    }

    clear_user_session(state)

    assert state["app_view"] == "Query assistant"
    assert state["unrelated"] == "keep"
    assert all(
        key not in state
        for key in (
            "configured_database_profile",
            "database_profile",
            "history",
            "conversation",
            "last_response",
            "question_input",
        )
    )
