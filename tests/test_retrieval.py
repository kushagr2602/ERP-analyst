"""Tests for schema retrieval (RAG).

Embeddings are faked so these run offline and deterministically -- the logic
under test is ranking, foreign-key expansion, and the small-schema bypass,
none of which need a real embedding model.
"""

from __future__ import annotations

import numpy as np
import pytest
import sqlalchemy as sa

from app.utils.database import get_fk_graph, get_schema_info
from app.utils.retrieval import SchemaIndex, select_tables, table_document

DDL = """
create table customers (id integer primary key, name text);
create table orders (id integer primary key, customer_id integer references customers(id), total real);
create table order_items (id integer primary key, order_id integer references orders(id),
                          product_id integer references products(id), qty integer);
create table products (id integer primary key, name text, supplier_id integer references suppliers(id));
create table suppliers (id integer primary key, name text);
create table employees (id integer primary key, name text);
create table invoices (id integer primary key, order_id integer references orders(id));
create table inventory (id integer primary key, product_id integer references products(id), qty integer);
create table contacts (id integer primary key, customer_id integer references customers(id));
create table shipments (id integer primary key, order_id integer references orders(id));
"""


@pytest.fixture
def engine():
    eng = sa.create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        for stmt in filter(str.strip, DDL.split(";")):
            conn.execute(sa.text(stmt))
    return eng


def fake_index(engine, ranked_first: str) -> SchemaIndex:
    """Index whose similarity ordering we control: `ranked_first` scores highest."""
    fk = get_fk_graph(engine)
    tables = sorted(fk)
    dim = len(tables)
    # identity rows -> similarity with query vector = that row's weight
    emb = np.eye(dim, dtype=np.float32)
    idx = SchemaIndex(tables=tables, embeddings=emb, fk_graph=fk)
    idx._query = np.zeros(dim, dtype=np.float32)  # type: ignore[attr-defined]
    idx._query[tables.index(ranked_first)] = 1.0  # type: ignore[attr-defined]
    return idx


def test_fk_graph_is_bidirectional(engine):
    fk = get_fk_graph(engine)
    assert "customers" in fk["orders"], "orders -> customers edge missing"
    assert "orders" in fk["customers"], "reverse edge missing; joins work both ways"


def test_small_schema_bypasses_retrieval(engine, monkeypatch):
    """Under the threshold, every table is returned and no embedding call is made."""
    fk = {t: set() for t in ["a", "b", "c"]}
    idx = SchemaIndex(tables=sorted(fk), embeddings=np.eye(3, dtype=np.float32), fk_graph=fk)

    def boom(*a, **k):
        raise AssertionError("embed() must not be called below the threshold")

    monkeypatch.setattr("app.utils.retrieval.embed", boom)
    tables, trace = select_tables("anything", idx, api_key="unused")

    assert tables == ["a", "b", "c"]
    assert trace["used_retrieval"] is False


def test_retrieval_expands_along_foreign_keys(engine, monkeypatch):
    """order_items alone is useless -- its FK neighbours must come along."""
    idx = fake_index(engine, ranked_first="order_items")
    monkeypatch.setattr("app.utils.retrieval.embed", lambda t, k: idx._query[None, :])

    tables, trace = select_tables("line items", idx, api_key="unused", top_k=1)

    assert trace["used_retrieval"] is True
    assert trace["retrieved"] == ["order_items"]
    assert "orders" in tables and "products" in tables, "joinable tables were dropped"
    assert set(trace["added_by_fk"]) == {"orders", "products"}


def test_retrieval_returns_subset_not_everything(engine, monkeypatch):
    """Retrieval must actually narrow the schema, or it is pointless."""
    idx = fake_index(engine, ranked_first="suppliers")
    monkeypatch.setattr("app.utils.retrieval.embed", lambda t, k: idx._query[None, :])

    tables, _ = select_tables("suppliers", idx, api_key="unused", top_k=1)
    assert len(tables) < idx.n_tables


def test_embedding_document_differs_from_prompt_schema(engine):
    """The embedded text is natural language; the prompt text is precise DDL."""
    doc = table_document(engine, "order_items")
    prompt_schema = get_schema_info(engine, only_tables=["order_items"])

    assert "order items" in doc, "underscores should be stripped for embedding"
    assert "INTEGER" not in doc, "type noise should not be embedded"
    assert "INTEGER" in prompt_schema, "the prompt still needs real types"


def test_schema_info_filters_to_requested_tables(engine):
    only = get_schema_info(engine, only_tables=["customers"])
    assert "Table: customers" in only
    assert "Table: orders" not in only
