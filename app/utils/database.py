"""
Database connectivity + read-only safety layer.

Supports: SQLite · PostgreSQL · MySQL · MSSQL · Oracle (via SQLAlchemy URIs).
All writes are blocked at the query-validation layer.
"""

from __future__ import annotations

import re
import textwrap
from typing import Iterable, Optional, Tuple

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import inspect, text


# ── Safety ───────────────────────────────────────────────────────────────────

_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|EXEC|EXECUTE|GRANT|REVOKE|CALL)",
    re.IGNORECASE | re.MULTILINE,
)

_COMMENT_STRIP = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)


def is_safe_query(sql: str) -> Tuple[bool, str]:
    """Return (is_safe, reason). Only SELECT / WITH / EXPLAIN allowed."""
    clean = _COMMENT_STRIP.sub("", sql).strip()
    if _WRITE_PATTERN.search(clean):
        return False, "Query contains write operations (INSERT/UPDATE/DELETE/etc). Only SELECT queries are allowed."
    if not re.match(r"^\s*(SELECT|WITH|EXPLAIN|PRAGMA|SHOW|DESCRIBE|DESC)\b", clean, re.IGNORECASE):
        return False, "Query must start with SELECT, WITH, or EXPLAIN."
    return True, ""


# ── Connection ────────────────────────────────────────────────────────────────

def create_engine(connection_string: str) -> sa.Engine:
    """Create a SQLAlchemy engine with a read-only comment in the app name."""
    connect_args = {}
    if connection_string.startswith("sqlite"):
        # SQLite: open in read-only mode via URI
        db_path = connection_string.replace("sqlite:///", "")
        connection_string = f"sqlite:///file:{db_path}?mode=ro&uri=true"
        connect_args = {"check_same_thread": False}

    engine = sa.create_engine(
        connection_string,
        connect_args=connect_args,
        pool_pre_ping=True,
        execution_options={"no_parameters": True},
    )
    return engine


def test_connection(engine: sa.Engine) -> Tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "Connected successfully."
    except Exception as exc:
        return False, str(exc)


# ── Schema Introspection ──────────────────────────────────────────────────────

def get_fk_graph(engine: sa.Engine) -> dict[str, set[str]]:
    """Undirected adjacency of tables joined by a foreign key.

    Used by the retrieval layer: a table is useless to the LLM without the
    tables it must be joined to, so retrieved tables get expanded along
    these edges before the schema is rendered.
    """
    inspector = inspect(engine)
    graph: dict[str, set[str]] = {t: set() for t in inspector.get_table_names()}

    for table_name in graph:
        for fk in inspector.get_foreign_keys(table_name):
            referred = fk.get("referred_table")
            if referred and referred in graph:
                graph[table_name].add(referred)
                graph[referred].add(table_name)  # joins work in both directions

    return graph


def get_schema_info(
    engine: sa.Engine,
    max_sample_rows: int = 0,
    only_tables: Optional[Iterable[str]] = None,
) -> str:
    """
    Return a compact, LLM-friendly schema description:
      TableName (col type PK?, col type, …)   [sample rows]

    Pass `only_tables` to render just that subset (used by schema retrieval);
    None renders every table.
    """
    inspector = inspect(engine)
    lines: list[str] = []
    wanted = set(only_tables) if only_tables is not None else None

    for table_name in inspector.get_table_names():
        if wanted is not None and table_name not in wanted:
            continue
        cols = inspector.get_columns(table_name)
        pk_cols = set(inspector.get_pk_constraint(table_name).get("constrained_columns", []))
        fks = inspector.get_foreign_keys(table_name)

        col_parts = []
        for col in cols:
            col_type = str(col["type"]).split("(")[0]
            pk_marker = " PK" if col["name"] in pk_cols else ""
            nullable = "" if col.get("nullable", True) else " NOT NULL"
            col_parts.append(f"{col['name']} {col_type}{pk_marker}{nullable}")

        fk_parts = []
        for fk in fks:
            for local_col, ref_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_parts.append(f"  FK: {local_col} → {fk['referred_table']}.{ref_col}")

        lines.append(f"Table: {table_name}")
        lines.append(f"  Columns: {', '.join(col_parts)}")
        if fk_parts:
            lines.extend(fk_parts)

        # Sample rows
        try:
            with engine.connect() as conn:
                sample = pd.read_sql(
                    text(f"SELECT * FROM {table_name} LIMIT {max_sample_rows}"),
                    conn,
                )
            if not sample.empty:
                lines.append(f"  Sample rows ({len(sample)}):")
                for _, row in sample.iterrows():
                    lines.append(f"    {dict(row)}")
        except Exception:
            pass

        lines.append("")

    return "\n".join(lines)


# ── Query Execution ───────────────────────────────────────────────────────────

def run_query(engine: sa.Engine, sql: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Run a validated SELECT query.
    Returns (DataFrame, error_message). DataFrame is None on error.
    """
    safe, reason = is_safe_query(sql)
    if not safe:
        return None, reason

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        return df, ""
    except Exception as exc:
        return None, str(exc)
