"""Synchronize an exact ticker between three Min Invest EOD analysis tabs.

UI-only, session-local and read-only. Does not alter filters, prices, signals,
or stock analysis. A non-symbol search (company name, multiple codes) stays local.
"""
from __future__ import annotations

import re

_SHARED = "min_eod_3tab_shared_symbol"
_LAST = "min_eod_3tab_last_widget"
_PATTERN = re.compile(r"[A-Z]{3,5}")


def _exact_symbol(value):
    text = str(value or "").strip().upper()
    return text if _PATTERN.fullmatch(text) else ""


def before(widget_key, state=None):
    """Preload the current shared ticker only on a switch between tabs.

    Call BEFORE creating st.text_input(key=widget_key); Streamlit forbids
    mutating the backing key after the widget is instantiated on a rerun.
    """
    if state is None:
        import streamlit as st
        state = st.session_state
    if state.get(_LAST) != widget_key:
        symbol = _exact_symbol(state.get(_SHARED, ""))
        if symbol:
            state[widget_key] = symbol
        state[_LAST] = widget_key


def remember(widget_key, state=None):
    """Copy single ticker to shared state on actual widget edit, not a rerun."""
    if state is None:
        import streamlit as st
        state = st.session_state
    symbol = _exact_symbol(state.get(widget_key, ""))
    if symbol:
        state[_SHARED] = symbol
    # Never turn a multi-code or company-name query into a false single ticker.
