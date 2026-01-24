"""
Training Catalogue Manager
==========================
Single entrypoint for the Streamlit application.
This is the only file Streamlit runs.

PRODUCTION: Requires DATABASE_URL and AUTH_* environment variables.
"""

import streamlit as st
from dotenv import load_dotenv

# Load .env file for local development (no-op in production if .env absent)
load_dotenv()

from components.font_loader import inject_custom_fonts
from components.styles import inject_global_styles
from components.sidebar_router import render_sidebar
from db import init_db, reset_query_counter, log_rerun_stats

# Import view modules
from views import dashboard, inventory, scrubbing, investment, tools


# Page registry - maps page_key to module
PAGES = {
    "dashboard": dashboard,
    "inventory": inventory,
    "scrubbing": scrubbing,
    "investment": investment,
    "tools": tools,
}


# Page config (only place this is called)
st.set_page_config(
    page_title="Training Catalogue Manager",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject global styles and fonts
inject_custom_fonts()
inject_global_styles()


# =============================================================================
# AUTHENTICATION GATE
# =============================================================================
from services.auth_service import validate_credentials

if not st.session_state.get("authentication_status"):
    # Center the login using Streamlit columns
    left, mid, right = st.columns([1, 1.2, 1])
    
    with mid:
        # All elements in ONE container = guaranteed grouping
        card = st.container()
        with card:
            st.markdown("## Training Catalogue Manager")
            st.caption("Sign in to continue")
            st.divider()
            
            # Native st.form = predictable layout, no widget fragmentation
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                
                # Forgot password (visual only)
                st.markdown("<small style='color: rgba(255,255,255,0.5);'><a href='#' style='color: inherit; text-decoration: none;'>Forgot password?</a></small>", unsafe_allow_html=True)
                
                # Full-width button using Streamlit's built-in option (no CSS hack)
                submitted = st.form_submit_button("Log in", use_container_width=True)
            
            if submitted:
                success, display_name = validate_credentials(username, password)
                if success:
                    st.session_state["authentication_status"] = True
                    st.session_state["name"] = display_name
                    st.session_state["username"] = username
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    
    st.stop()


# =============================================================================
# DATABASE HEALTH CHECK
# =============================================================================
try:
    init_db()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()


# =============================================================================
# AUTHENTICATED APP
# =============================================================================

import time
from db import _logger as db_logger  # Use same logger that shows in Railway

# Wall-clock start (local to this rerun execution scope)
_rerun_start = time.time()

# Reset instrumentation counters at start of every rerun (before any DB calls)
reset_query_counter()

try:

    # Render sidebar (mode toggle + nav/assistant routing)
    render_sidebar(
        name=name,
        username=username,
        authenticator=authenticator,
        pages=PAGES
    )

    # Render active page (timed)
    active = st.session_state.get("active_page", "dashboard")
    page_module = PAGES.get(active, dashboard)
    
    page_start = time.time()
    page_module.render()
    page_ms = (time.time() - page_start) * 1000
    db_logger.info(f"PAGE TIMING: {active}={page_ms:.0f}ms")
finally:
    # Always log stats, even on error
    total_ms = (time.time() - _rerun_start) * 1000
    log_rerun_stats(total_ms)
