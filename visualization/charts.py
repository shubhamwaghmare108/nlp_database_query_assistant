"""
visualization/charts.py
------------------------
Analyzes a result DataFrame and automatically selects and builds an
appropriate Plotly chart. Also exposes explicit builders so the user
can override the automatic choice from the UI.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_MAX_CATEGORIES_FOR_PIE = 10


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return list(df.select_dtypes(include="number").columns)


def _datetime_columns(df: pd.DataFrame) -> list[str]:
    cols = list(df.select_dtypes(include="datetime").columns)
    # Also catch columns that are date-like strings, e.g. "order_date"
    for col in df.columns:
        if col in cols:
            continue
        if df[col].dtype == object:
            try:
                pd.to_datetime(df[col], errors="raise")
                cols.append(col)
            except (ValueError, TypeError):
                continue
    return cols


def _categorical_columns(df: pd.DataFrame) -> list[str]:
    numeric = set(_numeric_columns(df))
    datetime_cols = set(_datetime_columns(df))
    return [c for c in df.columns if c not in numeric and c not in datetime_cols]


def suggest_chart_type(df: pd.DataFrame) -> Optional[str]:
    """
    Returns one of: 'bar', 'line', 'scatter', 'pie', or None if no
    chart is suitable for this data shape.
    """
    if df.empty or len(df.columns) < 2:
        return None

    numeric_cols = _numeric_columns(df)
    datetime_cols = _datetime_columns(df)
    categorical_cols = _categorical_columns(df)

    if datetime_cols and numeric_cols:
        return "line"

    if len(numeric_cols) >= 2 and not categorical_cols:
        return "scatter"

    if categorical_cols and numeric_cols:
        n_categories = df[categorical_cols[0]].nunique()
        if n_categories <= _MAX_CATEGORIES_FOR_PIE and len(df) <= _MAX_CATEGORIES_FOR_PIE:
            # Part-to-whole heuristic: a single numeric column summed
            # roughly covers "the whole" and category count is small.
            return "pie"
        return "bar"

    return None


def build_chart(df: pd.DataFrame, chart_type: str) -> Optional[go.Figure]:
    """Build a Plotly figure of the requested type, or None if unsuitable."""
    if df.empty:
        return None

    numeric_cols = _numeric_columns(df)
    datetime_cols = _datetime_columns(df)
    categorical_cols = _categorical_columns(df)

    try:
        if chart_type == "bar" and categorical_cols and numeric_cols:
            return px.bar(df, x=categorical_cols[0], y=numeric_cols[0],
                          title=f"{numeric_cols[0]} by {categorical_cols[0]}")

        if chart_type == "line":
            x_col = datetime_cols[0] if datetime_cols else (
                categorical_cols[0] if categorical_cols else df.columns[0]
            )
            if not numeric_cols:
                return None
            return px.line(df, x=x_col, y=numeric_cols[0],
                            title=f"{numeric_cols[0]} over {x_col}")

        if chart_type == "scatter" and len(numeric_cols) >= 2:
            return px.scatter(df, x=numeric_cols[0], y=numeric_cols[1],
                               title=f"{numeric_cols[1]} vs {numeric_cols[0]}")

        if chart_type == "pie" and categorical_cols and numeric_cols:
            return px.pie(df, names=categorical_cols[0], values=numeric_cols[0],
                          title=f"{numeric_cols[0]} share by {categorical_cols[0]}")

        if chart_type == "table":
            return go.Figure(
                data=[go.Table(
                    header=dict(values=list(df.columns)),
                    cells=dict(values=[df[c] for c in df.columns]),
                )]
            )
    except Exception:
        return None

    return None
