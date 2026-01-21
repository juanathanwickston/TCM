"""
Global Styles Module
====================
Centralized CSS for consistent styling across all pages.
"""

import streamlit as st


def inject_global_styles():
    """
    Inject global CSS styles for consistent layout across all pages.
    
    Call this once per page, immediately after st.set_page_config() and inject_custom_fonts().
    
    Provides:
    - Zero top padding (content starts at top)
    - Hidden Streamlit header bar
    - Full-height data tables
    - Consistent spacing
    """
    st.markdown("""
<style>
    /* Remove all top padding from main content area */
    .stApp > .main > .block-container {
        padding-top: 24px !important;
        margin-top: 0px !important;
        padding-bottom: 0px !important;
    }
    
    /* LAYOUT STABILITY: Prevent sidebar resize from causing main content reflow */
    .stApp > .main {
        contain: layout style;
        overflow-x: hidden;
    }
    
    /* Prevent scrollbar-induced layout shift */
    html {
        overflow-y: scroll;
    }
    
    /* Hide Streamlit's default header bar */
    .stApp > header {
        display: none !important;
    }
    
    /* Add top padding for main block container */
    .stMainBlockContainer {
        padding-top: 2rem !important;
    }
    
    /* Make data tables fill available viewport height */
    [data-testid="stDataFrame"] {
        height: calc(100vh - 280px) !important;
    }
    [data-testid="stDataFrame"] > div {
        height: 100% !important;
    }
    
    /* =========================================================================
       SIDEBAR: Mode Toggle (Top, Centered, Minimal Black/White)
       ========================================================================= */
    
    /* Tighten sidebar padding */
    section[data-testid="stSidebar"] > div:first-child {
        padding: 8px !important;
    }
    
    /* Mode toggle container - centered, minimal */
    section[data-testid="stSidebar"] [data-testid="stRadio"] {
        margin: 0 auto 8px auto !important;
        padding: 0 !important;
        display: flex !important;
        justify-content: center !important;
        transform: scale(0.7);
        transform-origin: center top;
        filter: grayscale(100%);
        opacity: 0.6;
    }
    
    section[data-testid="stSidebar"] [data-testid="stRadio"]:hover {
        opacity: 1;
    }
    
    /* Radio horizontal layout */
    section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
        display: flex !important;
        flex-wrap: nowrap !important;
        gap: 6px !important;
        justify-content: center !important;
    }
    
    /* Remove extra margins around nav buttons */
    section[data-testid="stSidebar"] div[data-testid="stButton"] {
        margin: 0 !important;
    }
    
    /* =========================================================================
       SIDEBAR: Nav buttons - Microsoft Fluent style
       ========================================================================= */
    
    /* Nav button base: flat, full width, 44px height */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        width: 100% !important;
        height: 44px !important;
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        padding: 0 12px !important;
        border-radius: 8px !important;
    }
    
    /* Force label container to left-align */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button > div {
        display: flex !important;
        justify-content: flex-start !important;
    }
    
    /* Label text: left aligned */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
        text-align: left !important;
        margin: 0 !important;
    }
    
    /* Hover state: subtle tint */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
        background: rgba(0, 0, 0, 0.04) !important;
    }
    
    /* Selected item (disabled button): highlight */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled {
        opacity: 1 !important;
        background: rgba(0, 0, 0, 0.08) !important;
        color: inherit !important;
        cursor: default !important;
        position: relative !important;
    }
    
    /* Left accent bar for selected item */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled::before {
        content: "" !important;
        position: absolute !important;
        left: 0 !important;
        top: 0 !important;
        width: 3px !important;
        height: 100% !important;
        background: #2563eb !important;
        border-radius: 0 2px 2px 0 !important;
    }
    
    /* =========================================================================
       SCRUBBING: Button Color Semantics (CRITICAL)
       ========================================================================= */
    
    /* PASS = Green (safe, primary, default) */
    button[kind="primary"],
    button.pass-btn {
        background-color: #16a34a !important;
        border-color: #16a34a !important;
        color: white !important;
    }
    
    button[kind="primary"]:hover,
    button.pass-btn:hover {
        background-color: #15803d !important;
        border-color: #15803d !important;
    }
    
    /* HOLD = Amber (neutral, secondary) */
    button.hold-btn {
        background-color: #f59e0b !important;
        border-color: #f59e0b !important;
        color: white !important;
    }
    
    button.hold-btn:hover {
        background-color: #d97706 !important;
        border-color: #d97706 !important;
    }
    
    button.hold-btn:disabled {
        background-color: #fcd34d !important;
        border-color: #fcd34d !important;
        opacity: 0.6 !important;
    }
    
    /* BLOCK = Red (destructive, separated) */
    button.block-btn {
        background-color: transparent !important;
        border: 2px solid #dc2626 !important;
        color: #dc2626 !important;
    }
    
    button.block-btn:hover {
        background-color: #dc2626 !important;
        color: white !important;
    }
    
    button.block-btn:disabled {
        border-color: #fca5a5 !important;
        color: #fca5a5 !important;
        opacity: 0.6 !important;
    }
    
    /* Undo button - visually secondary */
    button.undo-btn {
        background: transparent !important;
        border: none !important;
        color: rgba(0, 0, 0, 0.5) !important;
        font-size: 0.85rem !important;
    }
    
    button.undo-btn:hover {
        color: rgba(0, 0, 0, 0.8) !important;
    }
    
    /* =========================================================================
       SCRUBBING: Signals (muted, inline)
       ========================================================================= */
    
    .signals-line {
        font-size: 0.8rem;
        color: rgba(0, 0, 0, 0.5);
        margin: 4px 0 12px 0;
    }
</style>
""", unsafe_allow_html=True)


