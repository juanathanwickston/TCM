"""
Scrubbing View
==============
Queue-based triage: Include / Modify / Sunset workflow.

UI SPEC:
- 30/70 layout ALWAYS renders
- Status dropdown: Include, Modify, Sunset
- Audience required for Include/Modify
- Notes required for Modify/Sunset
- Save + Save and Next buttons
"""

import streamlit as st
import json

from db import get_active_containers, update_container_scrub, update_sales_stage
from services.scrub_rules import (
    normalize_status, CANONICAL_SCRUB_STATUSES, CANONICAL_AUDIENCES,
    VALID_SCRUB_REASONS, REASON_LABELS
)
from services.sales_stage import SALES_STAGES, SALES_STAGE_LABELS
from services.signal_service import compute_duplicate_map, compute_signals, get_flag_display_text
from components.layout import page_footer


# =============================================================================
# Constants
# =============================================================================

QUEUE_FILTERS = ["Unreviewed", "Include", "Modify", "Sunset", "All"]


# =============================================================================
# Helper Functions
# =============================================================================

def get_display_type(container: dict) -> str:
    """Compute display type from container."""
    if container.get('container_type') == 'folder':
        return 'FOLDER'
    if container.get('container_type') == 'links':
        return 'LINK'
    name = container.get('display_name', '')
    if '.' in name:
        return name.rsplit('.', 1)[-1].upper()
    return 'FILE'


def truncate_name(name: str, max_len: int = 40) -> str:
    """Truncate name for display with ellipsis."""
    if len(name) <= max_len:
        return name
    return name[:max_len-1] + "…"


def filter_queue(containers: list, queue_filter: str) -> list:
    """Filter containers using normalize_status for deterministic filtering."""
    if queue_filter == "All":
        return containers
    return [c for c in containers if normalize_status(c.get('scrub_status')) == queue_filter]


def compute_queue_counts(containers: list) -> dict:
    """Compute counts for each queue filter using normalize_status."""
    counts = {'Unreviewed': 0, 'Include': 0, 'Modify': 0, 'Sunset': 0, 'total': len(containers)}
    for c in containers:
        normalized = normalize_status(c.get('scrub_status'))
        if normalized in counts:
            counts[normalized] += 1
    return counts


def validate_and_save(container: dict, status: str, notes: str, sales_stage: str | None = None, advance: bool = False) -> bool:
    """
    Validate and save scrub decision. Returns True if saved successfully.
    Audience is not managed here - edited in Inventory.
    Sales Stage is optional - blank is allowed and sets NULL.
    """
    # Validate status is canonical
    if status not in CANONICAL_SCRUB_STATUSES:
        st.error(f"Invalid status: {status}. Must be Include, Modify, or Sunset.")
        return False
    
    # Validate notes required for Modify/Sunset
    if status in ('Modify', 'Sunset') and not notes.strip():
        st.error("Notes are required for Modify and Sunset.")
        return False
    
    # Save scrub decision (audience managed in Inventory)
    update_container_scrub(
        container_key=container['container_key'],
        decision=status,
        owner='',
        notes=notes.strip() if notes else None,
        reasons=None,
    )
    
    # Save sales_stage (optional - None clears it)
    update_sales_stage(
        container_key=container['container_key'],
        stage=sales_stage if sales_stage else None
    )
    
    st.toast("Saved")
    
    # Handle advance
    if advance:
        if 'selected_queue_idx' in st.session_state:
            st.session_state.selected_queue_idx += 1
    
    return True


# =============================================================================
# Main Content
# =============================================================================

def render():
    """Main scrubbing content - Include/Modify/Sunset workflow."""
    
    # Scrubbing-specific scoped CSS
    st.markdown("""
<style>
    /* =========================================================================
       SCRUBBING: Microsoft-style Queue List (radio-based)
       SCOPED to main content area only - do NOT affect sidebar toggle
       ========================================================================= */
    
    /* Remove radio button circles, make flat rows - MAIN CONTENT ONLY */
    section[data-testid="stMain"] div[data-testid="stRadio"] > div {
        gap: 0 !important;
    }
    
    section[data-testid="stMain"] div[data-testid="stRadio"] label {
        padding: 10px 12px !important;
        margin: 0 !important;
        border: none !important;
        background: transparent !important;
        border-radius: 0 !important;
        cursor: pointer !important;
        border-left: 3px solid transparent !important;
        transition: all 0.15s ease !important;
    }
    
    section[data-testid="stMain"] div[data-testid="stRadio"] label:hover {
        background: rgba(0, 0, 0, 0.04) !important;
    }
    
    /* Selected row: GREY highlight matching hover - MAIN CONTENT ONLY */
    section[data-testid="stMain"] div[data-testid="stRadio"] label[data-checked="true"],
    section[data-testid="stMain"] div[data-testid="stRadio"] input:checked + div {
        background: rgba(0, 0, 0, 0.04) !important;
        border-left-color: #666 !important;
        font-weight: 500 !important;
    }
    
    /* Hide the radio circle indicator - MAIN CONTENT ONLY */
    section[data-testid="stMain"] div[data-testid="stRadio"] label > div:first-child {
        display: none !important;
    }
    
    /* Row text styling - MAIN CONTENT ONLY */
    section[data-testid="stMain"] div[data-testid="stRadio"] label p {
        margin: 0 !important;
        font-size: 0.875rem !important;
        line-height: 1.4 !important;
    }
    
    /* =========================================================================
       SCRUBBING: Layout Constraints
       ========================================================================= */
    
    /* Max-width for readable content */
    .stApp > .main > .block-container {
        max-width: 1200px !important;
    }
    
    /* =========================================================================
       SCRUBBING: Card Sections (bordered containers for visual structure)
       ========================================================================= */
    
    /* Enhanced borders for st.container(border=True) on Scrubbing page */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid rgba(0, 0, 0, 0.12) !important;
        border-radius: 8px !important;
        background: rgba(0, 0, 0, 0.02) !important;
        padding: 16px !important;
        margin-bottom: 12px !important;
    }
    
    /* =========================================================================
       SCRUBBING: Ensure primary button stays GREEN
       ========================================================================= */
    
    button[data-testid="stBaseButton-primary"],
    button[kind="primary"],
    .stButton button[kind="primary"] {
        background-color: #16a34a !important;
        border-color: #16a34a !important;
        color: white !important;
    }
    
    button[data-testid="stBaseButton-primary"]:hover,
    button[kind="primary"]:hover,
    .stButton button[kind="primary"]:hover {
        background-color: #15803d !important;
        border-color: #15803d !important;
    }
</style>
""", unsafe_allow_html=True)
    
    # Scrubbing-only marker for CSS scoping (kept for reference, though CSS is now local)
    st.markdown('<div id="scrubbing-page-marker"></div>', unsafe_allow_html=True)
    
    containers = get_active_containers()
    
    if not containers:
        counts = {'Unreviewed': 0, 'Include': 0, 'Modify': 0, 'Sunset': 0, 'total': 0}
    else:
        counts = compute_queue_counts(containers)
    
    # =========================
    # HEADER BAR
    # =========================
    header_cols = st.columns([0.25, 0.5, 0.25])
    
    with header_cols[0]:
        queue_filter = st.selectbox(
            "Filter", QUEUE_FILTERS, index=0,
            key="scrub_queue_filter", label_visibility="collapsed"
        )
    
    with header_cols[2]:
        total = counts.get('total', 0)
        unreviewed = counts.get('Unreviewed', 0)
        reviewed = max(0, total - unreviewed)
        st.markdown(f"**{reviewed}** out of {total} items reviewed")
    
    # Handle no inventory
    if not containers:
        queue_col, review_col = st.columns([0.3, 0.7])
        with queue_col:
            st.markdown("##### Queue")
            st.info("No containers loaded.")
        with review_col:
            st.markdown("### Import content first")
            st.write("Use **Tools → Sync** to load your training catalog.")
            if st.button("Go to Tools"):
                st.session_state.active_page = "tools"
                st.rerun()
        page_footer("Stage 2 | Training Catalogue Manager")
        return
    
    # Filter queue
    filtered = filter_queue(containers, queue_filter)
    filtered = sorted(filtered, key=lambda c: (-(c.get('resource_count') or 0), c.get('relative_path', '')))
    
    # =========================
    # 30/70 LAYOUT (always render)
    # =========================
    queue_col, review_col = st.columns([0.3, 0.7])
    
    if 'selected_queue_idx' not in st.session_state:
        st.session_state.selected_queue_idx = 0
    if filtered and st.session_state.selected_queue_idx >= len(filtered):
        st.session_state.selected_queue_idx = 0
    
    # =========================
    # LEFT: Queue Panel
    # =========================
    with queue_col:
        st.markdown("##### Queue")
        
        if not filtered:
            st.caption(f"No items in '{queue_filter}'")
        else:
            # Render queue as flat list using radio
            queue_labels = [truncate_name(c.get('display_name', 'Unnamed')) for c in filtered[:50]]
            
            selected_idx = st.radio(
                "Select item",
                options=range(len(queue_labels)),
                index=min(st.session_state.selected_queue_idx, len(queue_labels) - 1),
                format_func=lambda i: queue_labels[i],
                key="queue_selection",
                label_visibility="collapsed"
            )
            
            if selected_idx != st.session_state.selected_queue_idx:
                st.session_state.selected_queue_idx = selected_idx
                st.rerun()
    
    # =========================
    # RIGHT: Review Panel
    # =========================
    with review_col:
        if not filtered:
            pass  # Left panel already shows the empty state message
        else:
            selected = filtered[st.session_state.selected_queue_idx]
            raw_status = selected.get('scrub_status')
            normalized_status = normalize_status(raw_status)
            
            # =========================
            # ASSET INFO (Card 1)
            # =========================
            with st.container(border=True):
                st.markdown(f"### {selected.get('display_name', 'Unnamed')}")
                st.caption(f"{get_display_type(selected)} · {selected.get('relative_path', '')}")
                
                # Resource count
                rc = selected.get('resource_count') or 1
                if rc > 1:
                    st.caption(f"📁 Contains {rc} resources")
                
                # Legacy/Unknown status warning
                if normalized_status == 'LegacyUnknown':
                    st.warning(f"⚠ Unknown status stored: '{raw_status}'")
                elif raw_status and raw_status not in CANONICAL_SCRUB_STATUSES and raw_status != 'not_reviewed':
                    st.caption(f"ℹ️ Legacy status: {raw_status} → displayed as {normalized_status}")
            
            # =========================
            # EDITOR FORM (Card 2)
            # =========================
            with st.container(border=True):
                # Status dropdown - canonical options only
                current_status_idx = 0
                if normalized_status in CANONICAL_SCRUB_STATUSES:
                    current_status_idx = CANONICAL_SCRUB_STATUSES.index(normalized_status) + 1
                
                status_options = [""] + list(CANONICAL_SCRUB_STATUSES)
                selected_status = st.selectbox(
                    "Status *",
                    options=status_options,
                    index=current_status_idx,
                    format_func=lambda x: "Select status..." if x == "" else x,
                    key=f"status_{selected['container_key']}"
                )
                
                # Sales Stage (optional) - per master prompt spec
                current_sales_stage = selected.get('sales_stage')
                stage_options = [""] + [k for k, _ in SALES_STAGES]
                stage_idx = 0
                if current_sales_stage and current_sales_stage in [k for k, _ in SALES_STAGES]:
                    stage_idx = stage_options.index(current_sales_stage)
                
                selected_sales_stage = st.selectbox(
                    "Sales Stage (optional)",
                    options=stage_options,
                    index=stage_idx,
                    format_func=lambda x: "—" if x == "" else SALES_STAGE_LABELS.get(x, x),
                    key=f"sales_stage_{selected['container_key']}"
                )
                
                # Audience is managed in Inventory, not Scrubbing
                
                # Notes (required for Modify/Sunset)
                notes_required = selected_status in ('Modify', 'Sunset')
                notes = st.text_area(
                    "Notes" + (" *" if notes_required else ""),
                    value=selected.get('scrub_notes') or '',
                    height=80,
                    key=f"notes_{selected['container_key']}"
                )
            
            st.markdown("")
            
            # =========================
            # SAVE BUTTONS (right-aligned, compact)
            # =========================
            # Layout: [ spacer ] [ Save ] [ Save and Next ]
            spacer_col, save_col, save_next_col = st.columns([3, 1, 1.5])
            
            is_last_item = st.session_state.selected_queue_idx >= len(filtered) - 1
            
            with save_col:
                if st.button("Save", type="secondary"):
                    if selected_status:
                        if validate_and_save(selected, selected_status, notes, selected_sales_stage or None, advance=False):
                            st.rerun()
                    else:
                        st.error("Please select a status.")
            
            with save_next_col:
                next_label = "Save and Next" if not is_last_item else "Save (End of queue)"
                if st.button(next_label, type="primary"):
                    if selected_status:
                        if validate_and_save(selected, selected_status, notes, selected_sales_stage or None, advance=not is_last_item):
                            st.rerun()
                    else:
                        st.error("Please select a status.")
            
    
    page_footer("Stage 2 | Training Catalogue Manager")
