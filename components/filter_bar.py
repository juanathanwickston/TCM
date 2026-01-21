"""
Global filter bar component.
Manages filter state in st.session_state["global_filters"].
"""

import streamlit as st
from typing import List, Dict, Any, Optional


GLOBAL_FILTER_KEY = "global_filters"


def init_global_filters(departments: List[str]) -> None:
    """Initialize global filter state if not exists."""
    if GLOBAL_FILTER_KEY not in st.session_state:
        st.session_state[GLOBAL_FILTER_KEY] = {
            "departments": departments.copy() if departments else []
        }


def get_active_filters() -> Dict[str, Any]:
    """Get current global filter state. Use this in all pages."""
    if GLOBAL_FILTER_KEY not in st.session_state:
        return {"departments": []}
    return st.session_state[GLOBAL_FILTER_KEY]


def set_department_filter(departments: List[str]) -> None:
    """Update department filter."""
    if GLOBAL_FILTER_KEY not in st.session_state:
        st.session_state[GLOBAL_FILTER_KEY] = {}
    st.session_state[GLOBAL_FILTER_KEY]["departments"] = departments


def clear_filters() -> None:
    """Clear all global filters."""
    if GLOBAL_FILTER_KEY in st.session_state:
        st.session_state[GLOBAL_FILTER_KEY] = {"departments": []}


def render_sidebar_filters(available_departments: List[str]) -> None:
    """Render global filter controls in sidebar."""
    init_global_filters(available_departments)
    
    st.sidebar.header("Filters")
    
    current = get_active_filters()
    
    selected = st.sidebar.multiselect(
        "Departments",
        options=available_departments,
        default=current.get("departments", available_departments),
        help="Filter affects all pages"
    )
    
    set_department_filter(selected)
    
    if st.sidebar.button("Clear Filters"):
        clear_filters()
        st.rerun()


def render_active_filter_pills() -> None:
    """Render active filter pills in content area."""
    filters = get_active_filters()
    depts = filters.get("departments", [])
    
    if depts:
        dept_list = ", ".join(depts[:3])
        if len(depts) > 3:
            dept_list += f" +{len(depts) - 3} more"
        st.caption(f"Viewing: **{dept_list}**")
    else:
        st.caption("Viewing: **All departments**")
