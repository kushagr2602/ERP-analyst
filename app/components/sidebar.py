"""Sidebar: DB connection + settings panel."""

import streamlit as st
import sqlalchemy as sa

from app.utils.database import create_engine, test_connection, get_schema_info


SAMPLE_QUESTIONS = [
    "What are the top 10 customers by total revenue?",
    "Show monthly sales trend for the last 12 months",
    "Which products have the lowest stock and highest demand?",
    "What is the order fulfilment rate by region?",
    "Show me open invoices older than 30 days",
    "Which suppliers have the most delayed deliveries?",
    "Revenue vs. Cost by product category this year",
    "Which sales reps exceeded their quota last quarter?",
    "What is the average days-to-pay by customer segment?",
    "Show inventory turnover ratio by warehouse",
]

DEMO_CONN = "sqlite:///data/erp_demo.db"


def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:1rem 0 0.5rem">
            <span style="font-size:2rem">📊</span><br>
            <span style="font-size:1.1rem;font-weight:700;letter-spacing:0.05em;color:#00D4FF">
                ERP Analyst Agent
            </span><br>
            <span style="font-size:0.7rem;color:#888;letter-spacing:0.15em">
                POWERED BY LANGCHAIN + GPT-4o
            </span>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # ── Database Connection ─────────────────────────────────────────────
        st.markdown("### 🔌 Database Connection")

        conn_type = st.selectbox(
            "Database type",
            ["SQLite (Demo)", "PostgreSQL", "MySQL", "SQL Server", "Custom URI"],
            help="Select your ERP database type",
        )

        if conn_type == "SQLite (Demo)":
            conn_str = DEMO_CONN
            st.info("Using the built-in demo ERP database.")
        elif conn_type == "PostgreSQL":
            host = st.text_input("Host", "localhost")
            port = st.text_input("Port", "5432")
            db = st.text_input("Database")
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            conn_str = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
        elif conn_type == "MySQL":
            host = st.text_input("Host", "localhost")
            port = st.text_input("Port", "3306")
            db = st.text_input("Database")
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            conn_str = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
        elif conn_type == "SQL Server":
            host = st.text_input("Server")
            port = st.text_input("Port", "1433")
            db = st.text_input("Database")
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            conn_str = f"mssql+pymssql://{user}:{pwd}@{host}:{port}/{db}?tds_version=7.0"
        else:
            conn_str = st.text_input(
                "Connection URI",
                placeholder="dialect+driver://user:pass@host/db",
            )

        if st.button("🔗 Connect", type="primary", use_container_width=True):
            with st.spinner("Connecting…"):
                try:
                    engine = create_engine(conn_str)
                    ok, msg = test_connection(engine)
                    if ok:
                        st.session_state.db_engine = engine
                        st.session_state.db_connected = True
                        st.session_state.connection_string = conn_str
                        st.session_state.db_dialect = engine.dialect.name
                        with st.spinner("Reading schema…"):
                            st.session_state.schema_info = get_schema_info(engine, max_sample_rows=0)
                        st.session_state.agent = None  # invalidate cached agent
                        st.session_state.schema_index = None  # re-embed for the new schema
                        st.success(f"✅ Connected! ({engine.dialect.name})")
                    else:
                        st.error(f"❌ {msg}")
                except Exception as exc:
                    st.error(f"❌ {exc}")

        if st.session_state.db_connected:
            st.markdown(
                f"**Status:** 🟢 Connected · `{st.session_state.db_dialect}`"
            )

        st.divider()

        # ── OpenAI API Key ──────────────────────────────────────────────────
        st.markdown("Your key here")
        api_key = st.text_input(
            "API Key",
            type="password",
            value=st.session_state.get("openai_api_key", ""),
            placeholder="sk-…",
            help="Your key is never stored or sent to third parties.",
        )
        if api_key:
            st.session_state["openai_api_key"] = api_key

        model = st.selectbox("Model", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"])
        st.session_state["model"] = model

        st.divider()

        # ── Sample Questions ────────────────────────────────────────────────
        st.markdown("### 💡 Sample Questions")
        for q in SAMPLE_QUESTIONS:
            if st.button(q, use_container_width=True, key=f"sq_{q[:20]}"):
                st.session_state["prefill_question"] = q

        st.divider()

        # ── Schema Viewer ───────────────────────────────────────────────────
        if st.session_state.schema_info:
            with st.expander("🗂 Schema", expanded=False):
                st.code(st.session_state.schema_info, language="text")

        # ── Clear Chat ──────────────────────────────────────────────────────
        if st.button("🗑 Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.query_history = []
            st.rerun()

        st.caption("v1.0 · Read-only · SELECT only")
