"""
Visualization layer — Plotly chart generation from DataFrames.
"""

from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ── Colour palette matching the app dark theme ────────────────────────────────
PALETTE = [
    "#00D4FF", "#FF6B6B", "#4ECDC4", "#FFE66D", "#A29BFE",
    "#FD79A8", "#6C5CE7", "#00B894", "#E17055", "#74B9FF",
]


def _numeric_cols(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes("number").columns.tolist()


def _text_cols(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes(exclude="number").columns.tolist()


def auto_visualize(
    df: pd.DataFrame,
    chart_type: str = "auto",
    title: str = "",
    x: Optional[str] = None,
    y: Optional[str] = None,
) -> Optional[go.Figure]:
    """
    Given a DataFrame and an optional chart type hint, return a Plotly figure.
    Returns None if visualization is not meaningful (e.g., single-row result).
    """
    if df is None or df.empty:
        return None

    num_cols = _numeric_cols(df)
    txt_cols = _text_cols(df)

    # Auto-detect chart type
    if chart_type == "auto" or chart_type == "table":
        if len(df) <= 1:
            return None
        if len(num_cols) >= 2 and len(txt_cols) == 0:
            chart_type = "scatter"
        elif len(txt_cols) >= 1 and len(num_cols) >= 1:
            chart_type = "bar"
        else:
            return None

    # Resolve x / y axes
    x_col = x or (txt_cols[0] if txt_cols else (num_cols[0] if len(num_cols) > 1 else None))
    y_col = y or (num_cols[0] if num_cols else None)

    fig = None

    try:
        if chart_type == "bar":
            if x_col and y_col:
                df_sorted = df.sort_values(y_col, ascending=False).head(30)
                fig = px.bar(
                    df_sorted,
                    x=x_col,
                    y=y_col,
                    title=title or f"{y_col} by {x_col}",
                    color=y_col,
                    color_continuous_scale=["#1a1a2e", "#00D4FF"],
                    text_auto=".2s",
                )
                fig.update_traces(textposition="outside")

        elif chart_type == "line":
            if x_col and y_col:
                fig = px.line(
                    df,
                    x=x_col,
                    y=num_cols if len(num_cols) > 1 else y_col,
                    title=title or f"{y_col} over {x_col}",
                    markers=True,
                    color_discrete_sequence=PALETTE,
                )

        elif chart_type == "pie":
            if x_col and y_col:
                df_pie = df.head(12)  # cap slices
                fig = px.pie(
                    df_pie,
                    names=x_col,
                    values=y_col,
                    title=title or f"{y_col} distribution",
                    color_discrete_sequence=PALETTE,
                    hole=0.4,
                )

        elif chart_type == "scatter":
            if len(num_cols) >= 2:
                color_col = txt_cols[0] if txt_cols else None
                fig = px.scatter(
                    df,
                    x=num_cols[0],
                    y=num_cols[1],
                    color=color_col,
                    title=title or f"{num_cols[0]} vs {num_cols[1]}",
                    color_discrete_sequence=PALETTE,
                    hover_data=df.columns.tolist(),
                )

        elif chart_type == "heatmap":
            if len(num_cols) >= 1 and len(txt_cols) >= 2:
                pivot = df.pivot_table(
                    index=txt_cols[0],
                    columns=txt_cols[1],
                    values=num_cols[0],
                    aggfunc="sum",
                    fill_value=0,
                )
                fig = px.imshow(
                    pivot,
                    title=title or "Heatmap",
                    color_continuous_scale="Blues",
                    aspect="auto",
                )

    except Exception as exc:
        st.warning(f"Chart generation issue: {exc}. Showing table instead.")
        return None

    if fig:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E0E0E0", family="IBM Plex Mono, monospace"),
            title_font_size=14,
            coloraxis_showscale=False,
            margin=dict(l=40, r=20, t=50, b=40),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        fig.update_xaxes(gridcolor="#2a2a3e", showline=False, tickfont_size=11)
        fig.update_yaxes(gridcolor="#2a2a3e", showline=False, tickfont_size=11)

    return fig


def render_results(
    df: pd.DataFrame,
    chart_type: str = "auto",
    title: str = "",
):
    """High-level helper: renders chart + download button + table."""
    if df is None or df.empty:
        st.warning("Query returned no rows.")
        return

    # Metrics strip
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows returned", f"{len(df):,}")
    col2.metric("Columns", len(df.columns))
    num_cols = _numeric_cols(df)
    if num_cols:
        col3.metric(f"Total {num_cols[0]}", f"{df[num_cols[0]].sum():,.2f}")

    # Chart
    if chart_type != "table" and len(df) > 1:
        fig = auto_visualize(df, chart_type=chart_type, title=title)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # Table
    with st.expander("📋 Raw Data", expanded=(chart_type == "table")):
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False)
        st.download_button(
            "⬇️ Download CSV",
            csv,
            "query_result.csv",
            "text/csv",
            use_container_width=True,
        )
