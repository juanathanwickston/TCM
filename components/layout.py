"""
Layout components for consistent page structure.
Stateless render-only functions.
"""

import streamlit as st


def page_header(title: str, description: str = None) -> None:
    """Render consistent page header."""
    st.title(title)
    if description:
        st.markdown(f"**{description}**")
    st.markdown("---")


def section_header(title: str) -> None:
    """Render section header."""
    st.header(title)


def section_divider() -> None:
    """Render subtle section divider."""
    st.markdown("---")



def empty_state(message: str, hint: str = None) -> None:
    """Render empty state message."""
    full_msg = message
    if hint:
        full_msg += f" {hint}"
    st.info(full_msg)


def loading_state(message: str = "Loading...") -> None:
    """Return spinner context with message."""
    return st.spinner(message)


def success_message(message: str = "Saved successfully") -> None:
    """Render success confirmation."""
    st.success(message)


def error_message(message: str, details: str = None) -> None:
    """Render error message with optional details."""
    st.error(message)
    if details:
        with st.expander("Show details"):
            st.code(details)
