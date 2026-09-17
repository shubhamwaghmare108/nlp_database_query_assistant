"""
utils/helpers.py
-----------------
Small shared utility functions used across modules.
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from typing import Iterator


def mask_secret(value: str, keep: int = 2) -> str:
    """Return a redacted version of a secret for safe logging/display."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


def strip_markdown_fences(text: str) -> str:
    """
    LLMs sometimes wrap SQL in ```sql ... ``` fences despite instructions
    not to. Strip them defensively before validation.
    """
    text = text.strip()
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


@contextmanager
def timer() -> Iterator[dict]:
    """
    Context manager that measures elapsed wall-clock time in seconds.
    Usage:
        with timer() as t:
            do_work()
        print(t["elapsed"])
    """
    result = {"elapsed": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed"] = round(time.perf_counter() - start, 4)
