"""Spend caps for the hosted demo.

If the deployment provides an OPENAI_API_KEY (Streamlit secrets), visitors can
try the app without supplying their own key -- which means the owner pays for
every request, so it is capped two ways:

  per session  one visitor cannot loop the expensive path
  global       total requests across all visitors, per process

Visitors who paste their own key are not limited: they are paying.

# ponytail: the global counter lives in a cached resource, so it is per-process
# and resets on redeploy or container recycle. Correct for a single free-tier
# instance; move to an external store only if the demo is ever scaled out.
"""

from __future__ import annotations

import os
import time

import streamlit as st

PER_SESSION_LIMIT = int(os.getenv("DEMO_PER_SESSION_LIMIT", "8"))
GLOBAL_DAILY_LIMIT = int(os.getenv("DEMO_GLOBAL_DAILY_LIMIT", "150"))


class DemoLimitReached(Exception):
    """Raised when the shared demo key is out of budget."""


@st.cache_resource
def _global_counter() -> dict:
    return {"count": 0, "window_start": time.time()}


def owner_key() -> str | None:
    """The deployment's own key, if one was configured."""
    try:
        key = st.secrets.get("OPENAI_API_KEY")  # type: ignore[attr-defined]
    except Exception:
        key = None
    return key or os.getenv("OPENAI_API_KEY") or None


def using_demo_key() -> bool:
    return bool(st.session_state.get("using_demo_key"))


def consume() -> None:
    """Record one billable request against the shared key, or raise."""
    if not using_demo_key():
        return  # visitor's own key -- not our budget

    counter = _global_counter()
    now = time.time()
    if now - counter["window_start"] > 24 * 60 * 60:
        counter.update(count=0, window_start=now)

    if counter["count"] >= GLOBAL_DAILY_LIMIT:
        raise DemoLimitReached(
            "The shared demo key has hit its daily budget. Paste your own OpenAI "
            "key in the sidebar to keep going, or try again tomorrow."
        )

    used = st.session_state.get("demo_calls", 0)
    if used >= PER_SESSION_LIMIT:
        raise DemoLimitReached(
            f"You have used the {PER_SESSION_LIMIT} free demo queries for this session. "
            "Paste your own OpenAI key in the sidebar for unlimited use."
        )

    st.session_state["demo_calls"] = used + 1
    counter["count"] += 1


def status() -> dict:
    counter = _global_counter()
    return {
        "session_used": st.session_state.get("demo_calls", 0),
        "session_limit": PER_SESSION_LIMIT,
        "global_used": counter["count"],
        "global_limit": GLOBAL_DAILY_LIMIT,
    }
