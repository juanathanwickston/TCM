"""
KPI card component for dashboard metrics.
Stateless render-only.
"""

import streamlit as st
from typing import Optional


def render_kpi_row(metrics: list) -> None:
    """
    Render a row of KPI cards.
    
    Args:
        metrics: List of dicts with keys: label, value, delta (optional)
    """
    cols = st.columns(len(metrics))
    
    for col, metric in zip(cols, metrics):
        with col:
            delta = metric.get("delta")
            col.metric(
                label=metric["label"],
                value=metric["value"],
                delta=delta
            )


def render_kpi_card(label: str, value: str, help_text: str = None) -> None:
    """Render single KPI metric."""
    st.metric(label=label, value=value, help=help_text)
