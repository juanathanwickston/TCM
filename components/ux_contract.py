"""
UX Behavior Contract
====================
This file documents the UI/UX rules for the Training Catalogue Manager.
All components and pages must follow these rules.

CLICKABLE ELEMENTS
------------------
- Stage tiles on Dashboard: CLICKABLE, navigate to stage pages
- KPI cards: STATIC, display only
- Filter pills: CLICKABLE, remove filter on click
- Table rows in expanders: STATIC, use explicit Save button
- Save/Submit buttons: CLICKABLE, explicit action

FILTER SCOPE
------------
- Department filter: GLOBAL, affects all pages
- Status/Bucket filters on pages: LOCAL, page-specific
- Global filters stored in: st.session_state["global_filters"]
- All pages must call: get_active_filters() from components.filter_bar

SAVE BEHAVIOR
-------------
- All saves require explicit button click
- No auto-save on rerun
- Show confirmation message after save
- Validate before save, show errors inline
- Refresh cache after successful save

STAGE STATUS (UI tiles)
-----------------------
- StageState.COMPLETE: green background
- StageState.IN_PROGRESS: blue background
- StageState.NOT_STARTED: gray background
- StageState.NEEDS_ATTENTION: red background

SCRUB STATUS (content)
----------------------
- not_reviewed: gray text
- keep: green text
- modify: blue text
- sunset: orange text
- gap: red text

INVEST DECISION (content)
-------------------------
- build: blue text
- buy: purple text
- assign_sme: teal text
- defer: gray text

EMPTY STATES
------------
- Every table/chart must show a message when empty
- Format: "No items found. [Actionable hint]"

LOADING STATES
--------------
- Use st.spinner with descriptive text
- Format: "Loading..." or "Saving..." not just spinner

CONFIRMATION STATES
-------------------
- Success: st.success("Saved successfully")
- Error: st.error("Failed: [reason]")
- Always visible, never silent
"""

from enum import Enum


class StageState(str, Enum):
    """Stage progress states for UI tiles."""
    COMPLETE = "complete"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"
    NEEDS_ATTENTION = "needs_attention"


# Color definitions (use in CSS or Streamlit styling)
STAGE_COLORS = {
    StageState.COMPLETE: "#22c55e",        # green
    StageState.IN_PROGRESS: "#3b82f6",     # blue
    StageState.NOT_STARTED: "#9ca3af",     # gray
    StageState.NEEDS_ATTENTION: "#ef4444", # red
}

SCRUB_COLORS = {
    "not_reviewed": "#6b7280",  # gray
    "keep": "#22c55e",          # green
    "modify": "#3b82f6",        # blue
    "sunset": "#f97316",        # orange
    "gap": "#ef4444",           # red
}

INVEST_COLORS = {
    "build": "#3b82f6",     # blue
    "buy": "#8b5cf6",       # purple
    "assign_sme": "#14b8a6", # teal
    "defer": "#6b7280",     # gray
}
