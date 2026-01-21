"""
Status chip component for scrub/invest status display.
Stateless render-only.
"""

import streamlit as st
from components.ux_contract import SCRUB_COLORS, INVEST_COLORS


# Text-only labels (no emojis)
SCRUB_LABELS = {
    "not_reviewed": "Not Reviewed",
    "keep": "Keep",
    "modify": "Modify",
    "sunset": "Sunset",
    "gap": "Gap",
}

INVEST_LABELS = {
    "build": "Build",
    "buy": "Buy",
    "assign_sme": "Assign SME",
    "defer": "Defer",
}


def get_scrub_label(status: str) -> str:
    """Get display label for scrub status."""
    return SCRUB_LABELS.get(status, status or "Not Reviewed")


def get_invest_label(decision: str) -> str:
    """Get display label for investment decision."""
    return INVEST_LABELS.get(decision, decision or "Pending")


def render_scrub_status(status: str) -> None:
    """Render scrub status as styled text."""
    label = get_scrub_label(status)
    color = SCRUB_COLORS.get(status, SCRUB_COLORS["not_reviewed"])
    st.markdown(f"**Status:** <span style='color:{color}'>{label}</span>", unsafe_allow_html=True)


def render_invest_decision(decision: str) -> None:
    """Render investment decision as styled text."""
    if not decision:
        st.markdown("**Decision:** Pending")
        return
    label = get_invest_label(decision)
    color = INVEST_COLORS.get(decision, "#6b7280")
    st.markdown(f"**Decision:** <span style='color:{color}'>{label}</span>", unsafe_allow_html=True)
