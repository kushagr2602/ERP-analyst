"""Schema retrieval (RAG) for SQL generation.

Problem this solves: the agent used to paste every table in the database into
the prompt. That is fine for a demo with 11 tables and impossible for a real
ERP with several hundred -- the schema alone would exhaust the context window,
and burying the 3 relevant tables among 300 measurably hurts SQL accuracy.

Pipeline:
  1. index   -- each table is rendered as text and embedded once per connection
  2. rank    -- the question is embedded and scored against every table by
                cosine similarity
  3. expand  -- top-K tables are widened along foreign keys, because a table
                is useless without the ones it must be joined to
  4. ground  -- only the selected subset is rendered into the prompt

No vector database: with hundreds of tables this is a few hundred vectors, and
an exact NumPy dot product over them is both faster and simpler than a nearest-
neighbour index.
# ponytail: exact search, O(n) per query. Swap in FAISS/pgvector only if the
# table count reaches the tens of thousands, where approximate search wins.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import sqlalchemy as sa
from openai import OpenAI

from app.utils.database import get_fk_graph, get_schema_info

EMBED_MODEL = "text-embedding-3-small"

# Below this many tables, retrieval cannot help: everything fits in the prompt
# comfortably, and filtering only risks dropping a table the query needed.
# The demo database has 11 tables, so this default keeps retrieval active there;
# raise it if you connect a small database and want the whole schema every time.
RETRIEVAL_MIN_TABLES = 8

DEFAULT_TOP_K = 5


@dataclass
class SchemaIndex:
    """Embedded schema for one database connection."""

    tables: list[str]
    embeddings: np.ndarray  # (n_tables, dim), L2-normalised
    fk_graph: dict[str, set[str]]

    @property
    def n_tables(self) -> int:
        return len(self.tables)


def _normalise(v: np.ndarray) -> np.ndarray:
    """L2-normalise rows so a dot product is the cosine similarity."""
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.clip(norms, 1e-12, None)


def embed(texts: list[str], api_key: str) -> np.ndarray:
    resp = OpenAI(api_key=api_key).embeddings.create(model=EMBED_MODEL, input=texts)
    return _normalise(np.array([d.embedding for d in resp.data], dtype=np.float32))


def table_document(engine: sa.Engine, table: str) -> str:
    """The text that gets embedded -- deliberately not the text sent to the LLM.

    The prompt needs precise DDL (types, PKs, NOT NULL). Embeddings do not:
    'INTEGER' and 'VARCHAR' appear in every table and only add noise. Ranking
    improves measurably when the document reads as natural language instead --
    underscores stripped, types dropped, related tables named.
    """
    inspector = sa.inspect(engine)
    cols = [c["name"].replace("_", " ") for c in inspector.get_columns(table)]
    refs = [fk["referred_table"] for fk in inspector.get_foreign_keys(table)]

    doc = f"{table.replace('_', ' ')}. Fields: {', '.join(cols)}."
    if refs:
        doc += f" Related to: {', '.join(sorted(set(refs)))}."
    return doc


def build_index(engine: sa.Engine, api_key: str) -> SchemaIndex:
    """Embed every table once. Cache this per connection -- it costs one API call."""
    fk_graph = get_fk_graph(engine)
    tables = sorted(fk_graph)
    docs = [table_document(engine, t) for t in tables]
    return SchemaIndex(tables=tables, embeddings=embed(docs, api_key), fk_graph=fk_graph)


def select_tables(
    question: str,
    index: SchemaIndex,
    api_key: str,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[str], dict]:
    """Pick the tables needed to answer `question`.

    Returns (table_names, trace) where trace explains the choice -- the UI shows
    it so the retrieval step is inspectable rather than a black box.
    """
    if index.n_tables < RETRIEVAL_MIN_TABLES:
        return list(index.tables), {
            "used_retrieval": False,
            "reason": f"only {index.n_tables} tables -- whole schema fits, retrieval skipped",
            "scores": [],
            "retrieved": list(index.tables),
            "added_by_fk": [],
        }

    scores = index.embeddings @ embed([question], api_key)[0]
    order = np.argsort(-scores)[:top_k]
    retrieved = [index.tables[i] for i in order]

    # A retrieved table is useless without what it joins to: pull in direct
    # FK neighbours so the model can actually write the JOIN.
    expanded = set(retrieved)
    for t in retrieved:
        expanded |= index.fk_graph.get(t, set())
    added_by_fk = sorted(expanded - set(retrieved))

    return sorted(expanded), {
        "used_retrieval": True,
        "reason": f"top-{top_k} of {index.n_tables} tables by cosine similarity, expanded along foreign keys",
        "scores": [(index.tables[i], round(float(scores[i]), 3)) for i in order],
        "retrieved": retrieved,
        "added_by_fk": added_by_fk,
    }


def retrieve_schema(
    question: str,
    engine: sa.Engine,
    index: SchemaIndex,
    api_key: str,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[str, dict]:
    """Full RAG step: rank, expand, then render only the selected tables."""
    tables, trace = select_tables(question, index, api_key, top_k)
    return get_schema_info(engine, only_tables=tables), trace
