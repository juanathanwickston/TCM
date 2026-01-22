"""
Sidebar Router
==============
Two-mode sidebar: Navigation | Assistant.
Mode selector at top (two dots, centered, no labels).
Persistence via st.session_state.
"""

import streamlit as st


# =============================================================================
# Session state initialization
# =============================================================================

def init_session_state():
    """Initialize all sidebar-related session state."""
    if "sidebar_mode" not in st.session_state:
        st.session_state.sidebar_mode = "nav"
    if "active_page" not in st.session_state:
        st.session_state.active_page = "dashboard"
    if "assistant_messages" not in st.session_state:
        st.session_state.assistant_messages = []


# =============================================================================
# Mode toggle (two dots, centered, no labels)
# =============================================================================

def render_mode_toggle():
    """
    Render the mode toggle at the top of the sidebar.
    Two radio dots, left-aligned, no visible text.
    
    NOTE: Must be called inside `with st.sidebar:` context.
    """
    st.radio(
        "mode",
        options=["nav", "assistant"],
        format_func=lambda x: "\u200b" if x == "nav" else "\u200c",
        horizontal=True,
        label_visibility="collapsed",
        key="sidebar_mode",
    )


# =============================================================================
# Navigation (custom nav buttons)
# =============================================================================

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("inventory", "Inventory"),
    ("scrubbing", "Scrubbing"),
    ("investment", "Investment"),
    ("tools", "Tools"),
]


def render_navigation():
    """
    Render navigation buttons in the sidebar.
    
    NOTE: Must be called inside `with st.sidebar:` context.
    """
    current = st.session_state.get("active_page", "dashboard")
    
    for page_key, label in NAV_ITEMS:
        is_selected = (page_key == current)
        
        # Selected = disabled only (CSS handles styling)
        if st.button(
            label,
            key=f"nav_{page_key}",
            use_container_width=True,
            disabled=is_selected
        ):
            st.session_state.active_page = page_key
            st.rerun()


# =============================================================================
# Assistant sidebar
# =============================================================================

def render_assistant_sidebar():
    """
    Render assistant chat UI in sidebar.
    ChatGPT-style: chat fills entire sidebar, input pinned at bottom.
    Visual demo only — no backend integration.
    """
    # CSS to make assistant fill entire sidebar height
    st.markdown("""
    <style>
        /* Make sidebar assistant container fill available height */
        [data-testid="stSidebar"] > div:first-child {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        
        /* Chat container fills remaining space */
        [data-testid="stSidebar"] .stChatMessage {
            flex-shrink: 0;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Header (compact)
    st.markdown("### 💬 Assistant")
    st.caption("Visual demo — not connected yet")
    
    # Conversation container (fills available space)
    # Using a large height to approximate full sidebar
    chat_box = st.container(height=600)
    with chat_box:
        with st.chat_message("assistant"):
            st.write("Hello! How can I help you today?")
        
        with st.chat_message("user"):
            st.write("How many resources are unreviewed?")
        
        with st.chat_message("assistant"):
            st.write("There are **45 resources** awaiting review.")
        
        with st.chat_message("user"):
            st.write("Which department has the most?")
        
        with st.chat_message("assistant"):
            st.write("Sales has 23, Operations has 15, HR has 7.")
    
    # Input (pinned at bottom)
    prompt = st.chat_input("Type your message...")
    if prompt:
        st.toast("Assistant is not connected yet. This is a visual demo.")


# =============================================================================
# Main sidebar entry point
# =============================================================================

def render_sidebar(
    name: str,
    username: str,
    authenticator,
    pages: dict
):
    """
    Main sidebar entry point. Renders mode toggle at top, then navigation.
    
    Args:
        name: User display name
        username: Username (pass-through)
        authenticator: Streamlit-Authenticator instance
        pages: Dict mapping page_key to module (with render() and optional render_sidebar())
    """
    init_session_state()
    
    with st.sidebar:
        # 1. IDENTITY BLOCK (top)
        st.markdown('''
        <div class="tcm-sidebar-identity">
            <p style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin: 0 0 0.25rem 0;">SIGNED IN AS</p>
            <p style="font-size: 1rem; font-weight: 500; color: rgb(49, 51, 63); margin: 0;"><strong>{}</strong></p>
        </div>
        '''.format(name), unsafe_allow_html=True)
        
        # 2. MODE TOGGLE - at top, centered
        render_mode_toggle()
        
        # 3. NAVIGATION - mode-dependent
        if st.session_state.sidebar_mode == "nav":
            # Navigation mode - nav only, no view hooks
            render_navigation()
        
        else:
            # Assistant mode
            render_assistant_sidebar()
        
        # 4. LOGOUT (after nav, visually separated)
        st.markdown("---")
        st.markdown('<div class="tcm-sidebar-logout">', unsafe_allow_html=True)
        authenticator.logout("🚪", "sidebar", key="logout_btn")
        st.markdown('</div>', unsafe_allow_html=True)


