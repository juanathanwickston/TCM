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
from services.auth_service import get_authenticator

# Create authenticator (reads cookie, sets session_state)
try:
    authenticator = get_authenticator()
except RuntimeError as e:
    st.error(f"Authentication configuration error: {e}")
    st.stop()

# Initialize variables
name = None
auth_status = None
username = None

# Check if already authenticated (from cookie)
# authenticator will have set session_state when reading cookie
if not st.session_state.get("authentication_status"):
    # NOT AUTHENTICATED - render login UI
    left, mid, right = st.columns([1, 1.5, 1])
    
    with mid:
        st.markdown("## Training Catalogue Manager")
        st.caption("Sign in to continue")
        st.divider()
        
        # Authenticator handles cookie set/read
        # For streamlit-authenticator 0.3.2: login(form_name, location)
        name, auth_status, username = authenticator.login('Login', 'main')
        
        # Visual element below form
        st.markdown("<small style='color: rgba(255,255,255,0.5);'>Forgot password?</small>", 
                    unsafe_allow_html=True)
    
    # Gate logic for unauthenticated path
    if auth_status is False:
        st.error("Invalid username or password")
    
    st.stop()  # HARD STOP - no app content when unauthenticated

# AUTHENTICATED - set session state for convenience
name = st.session_state.get("name")
username = st.session_state.get("username")


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
