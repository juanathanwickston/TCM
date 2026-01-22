"""
Page Frame Component
====================
Enforces consistent page structure across all views.
Prevents layout jumps by guaranteeing identical vertical structure.

CRITICAL: Do not modify without understanding the stability contract.
"""

import streamlit as st
from typing import Callable


def render_page_frame(
    title: str,
    subtitle: str,
    content_callable: Callable[[st.container], None],
    footer_text: str = "Stage 2 | Training Catalogue Manager"
) -> None:
    """
    Render a consistent page frame with guaranteed fixed layout.
    
    STABILITY CONTRACT:
    - Header area always renders title + subtitle (subtitle may be empty string)
    - Message container always exists (may be empty)
    - Footer always renders identically
    - No conditional mounting/unmounting allowed
    
    Args:
        title: Page title displayed at top
        subtitle: Subtitle text - REQUIRED, use "" if page has no subtitle
        content_callable: Function that receives message_container and renders page content
                         Signature: def _render(message_container: st.container)
        footer_text: Footer text displayed at bottom
    """
    # Scoped wrapper for CSS isolation - prevents global CSS pollution
    st.markdown('<div class="tcm-page-frame">', unsafe_allow_html=True)
    
    # Header area - ALWAYS renders both title and subtitle
    # Subtitle must be a string: "" means no subtitle but still reserves height
    st.title(title)
    st.caption(subtitle if subtitle else " ")  # Non-breaking space preserves height
    
    # Reserved message container - ALWAYS exists
    # Pages render messages INSIDE this container using 'with' context
    message_container = st.container()
    
    # Main content area - receives message_container for controlled messaging
    if content_callable:
        content_callable(message_container)
    
    # Footer - ALWAYS renders identically
    st.markdown("---")
    st.caption(footer_text)
    
    # Close scoped wrapper
    st.markdown('</div>', unsafe_allow_html=True)
