"""
ERP Data Analyst Agent — Main Streamlit Application
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.components.sidebar import render_sidebar
from app.components.chat import render_chat
from app.components.dashboard import render_dashboard
from app.utils.session import init_session_state

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ERP Analyst Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load Custom CSS ──────────────────────────────────────────────────────────
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "..", "assets", "styles.css")
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()
init_session_state()

# ── Layout ───────────────────────────────────────────────────────────────────
render_sidebar()

tab1, tab2 = st.tabs(["💬  Ask the Agent", "📈  Dashboard"])

with tab1:
    render_chat()

with tab2:
    render_dashboard()
