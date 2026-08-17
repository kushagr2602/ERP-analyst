"""
Chat component — NL → SQL → Results pipeline.
"""

from __future__ import annotations

import time
import streamlit as st

from app.utils.agent import generate_sql_direct, advise_chart, extract_sql
from app.utils.database import run_query, is_safe_query
from app.utils.charts import render_results
from app.utils.retrieval import build_index, retrieve_schema


def _render_retrieval_trace(thinking, trace: dict) -> None:
    """Show which tables were selected and why -- retrieval should be inspectable."""
    if not trace["used_retrieval"]:
        thinking.write(f"Using full schema ({trace['reason']}).")
        return

    ranked = ", ".join(f"{t} ({s})" for t, s in trace["scores"])
    thinking.write(f"Top matches by similarity: {ranked}")
    if trace["added_by_fk"]:
        thinking.write(f"Added for joins (foreign keys): {', '.join(trace['added_by_fk'])}")


def _require_db():
    if not st.session_state.db_connected:
        st.info("👈 Connect to a database in the sidebar to get started.")
        return False
    return True


def _require_key():
    if not st.session_state.get("openai_api_key"):
        st.warning("🔑 Enter your OpenAI API key in the sidebar.")
        return False
    return True


def _add_message(role: str, content: str, sql: str = "", df=None, chart_type: str = ""):
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "sql": sql,
        "df": df,
        "chart_type": chart_type,
        "timestamp": time.strftime("%H:%M"),
    })


def _render_message(msg: dict):
    role = msg["role"]
    avatar = "🧑‍💼" if role == "user" else "🤖"

    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])

        if msg.get("sql"):
            with st.expander("📝 Generated SQL", expanded=False):
                st.code(msg["sql"], language="sql")

                safe, reason = is_safe_query(msg["sql"])
                if safe:
                    st.success("✅ Query validated — read-only SELECT")
                else:
                    st.error(f"⛔ Safety check: {reason}")

        if msg.get("df") is not None:
            render_results(
                msg["df"],
                chart_type=msg.get("chart_type", "auto"),
                title=msg["content"][:60],
            )


def render_chat():
    # ── Guards ──────────────────────────────────────────────────────────────
    if not _require_db():
        return
    if not _require_key():
        return

    # ── Welcome ─────────────────────────────────────────────────────────────
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align:center;padding:3rem 1rem;opacity:0.7">
            <div style="font-size:3rem">📊</div>
            <h3 style="color:#00D4FF;margin:0.5rem 0">Ask anything about your ERP data</h3>
            <p style="color:#888;max-width:500px;margin:auto">
                Type a business question below and the AI will generate the SQL,
                run it safely (read-only), and visualize the results.
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ── History ──────────────────────────────────────────────────────────────
    for msg in st.session_state.messages:
        _render_message(msg)

    # ── Input ────────────────────────────────────────────────────────────────
    # Check for sidebar prefill
    prefill = st.session_state.pop("prefill_question", "")

    question = st.chat_input(
        "Ask a business question… e.g. 'Top 10 customers by revenue this year'",
    )

    if prefill and not question:
        question = prefill

    if not question:
        return

    # ── User message ─────────────────────────────────────────────────────────
    _add_message("user", question)
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(question)

    # ── Agent pipeline ───────────────────────────────────────────────────────
    with st.chat_message("assistant", avatar="🤖"):
        thinking = st.status("🧠 Analyzing your question…", expanded=True)

        try:
            # Step 0: Retrieve the relevant slice of the schema (RAG).
            # Embedding every table costs one API call, so the index is built
            # once per connection and cached; the sidebar clears it on connect.
            api_key = st.session_state["openai_api_key"]
            engine = st.session_state.db_engine

            if st.session_state.get("schema_index") is None:
                thinking.write("Indexing schema (one-off embedding pass)…")
                st.session_state.schema_index = build_index(engine, api_key)

            thinking.write("Retrieving relevant tables…")
            schema, trace = retrieve_schema(
                question=question,
                engine=engine,
                index=st.session_state.schema_index,
                api_key=api_key,
            )
            _render_retrieval_trace(thinking, trace)

            # Step 1: Generate SQL
            thinking.write("Generating SQL query…")
            sql = generate_sql_direct(
                question=question,
                schema=schema,
                dialect=st.session_state.db_dialect,
                openai_api_key=api_key,
                model=st.session_state.get("model", "gpt-4o"),
            )

            # Step 2: Safety check
            thinking.write("Validating query safety…")
            safe, reason = is_safe_query(sql)
            if not safe:
                thinking.update(label="⛔ Safety check failed", state="error")
                err_msg = f"I generated a query but it failed the safety check:\n\n**{reason}**\n\nOnly SELECT queries are permitted."
                st.markdown(err_msg)
                _add_message("assistant", err_msg)
                return

            # Step 3: Execute
            thinking.write("Executing query on database…")
            df, error = run_query(st.session_state.db_engine, sql)
            if error:
                thinking.update(label="❌ Query error", state="error")
                err_msg = f"The query returned an error:\n```\n{error}\n```\n\nTry rephrasing your question."
                st.markdown(err_msg)
                _add_message("assistant", err_msg, sql=sql)
                return

            # Step 4: Chart advice
            thinking.write("Choosing visualization…")
            chart_type = advise_chart(question, df.columns.tolist())

            thinking.update(label="✅ Done!", state="complete", expanded=False)

            # Step 5: Response
            row_word = "row" if len(df) == 1 else "rows"
            response = (
                f"Here are the results for **{question}**\n\n"
                f"Found **{len(df):,} {row_word}** across **{len(df.columns)} columns**."
            )
            st.markdown(response)

            with st.expander("📝 Generated SQL", expanded=False):
                st.code(sql, language="sql")
                st.success("✅ Query validated — read-only SELECT")

            render_results(df, chart_type=chart_type, title=question[:60])

            # Persist to history
            _add_message("assistant", response, sql=sql, df=df, chart_type=chart_type)
            st.session_state.query_history.append({
                "question": question,
                "sql": sql,
                "rows": len(df),
                "chart": chart_type,
            })

        except Exception as exc:
            thinking.update(label="❌ Error", state="error")
            err_msg = f"An error occurred: `{exc}`\n\nPlease check your API key and database connection."
            st.markdown(err_msg)
            _add_message("assistant", err_msg)
