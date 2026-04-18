"""Session state initialisation helpers."""

import streamlit as st


def init_session_state():
    defaults = {
        "messages": [],           # chat history
        "db_connected": False,    # DB connection flag
        "db_engine": None,        # SQLAlchemy engine
        "db_dialect": None,       # e.g. 'sqlite', 'postgresql'
        "schema_info": "",        # cached schema string
        "last_sql": "",           # last generated SQL
        "last_df": None,          # last result DataFrame
        "query_history": [],      # list of (question, sql, rows) tuples
        "agent": None,            # cached LangChain agent
        "connection_string": "",  # saved conn string
        "dark_mode": True,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
