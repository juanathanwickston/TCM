"""
Inventory View
==============
Browse training content with Department and Training Type filters.
Filters are DB-backed for consistency with metrics.
"""

import streamlit as st
import pandas as pd
import os
from pathlib import Path

from db import (
    get_active_containers_filtered,
    get_active_departments,
    get_active_training_types,
    update_audience_bulk,
    _logger as db_logger
)
from services.container_service import import_from_zip, TRAINING_TYPE_LABELS
from services.sales_stage import SALES_STAGES, SALES_STAGE_LABELS
from components.layout import section_divider, empty_state, success_message
from components.formatters import format_display_path
from components.page_frame import render_page_frame


# =============================================================================
# Filter State
# =============================================================================

def _init_filter_state():
    """Initialize session state for filters."""
    if "inv_department" not in st.session_state:
        st.session_state.inv_department = None
    if "inv_training_type" not in st.session_state:
        st.session_state.inv_training_type = None
    if "inv_sales_stage" not in st.session_state:
        st.session_state.inv_sales_stage = None  # None = All, "untagged" = NULL, else stage key


def _get_training_type_label(key: str) -> str:
    """Convert training type key to friendly display label."""
    return TRAINING_TYPE_LABELS.get(key, key.replace("_", " ").title())


# =============================================================================
# Sidebar hook - no longer used for tree selector
# =============================================================================

def render_sidebar():
    """
    Contextual sidebar content for Inventory page.
    Filters moved to main content area - sidebar is now minimal.
    """
    st.caption("Use filters in main content area to browse training resources.")


# =============================================================================
# Main content
# =============================================================================

def render():
    """Main inventory content with DB-backed filters."""
    
    def _render_content(message_container):
        _init_filter_state()
        
        # Check if any data exists
        departments = get_active_departments()
        
        if not departments:
            with message_container:
                st.warning("No content loaded yet.")
                st.info("Use the **Tools** page to import a ZIP file or sync with SharePoint.")
            
            # Quick import option
            st.subheader("Quick Import")
            zip_path = Path(__file__).parent.parent / "Payroc Training Catalogue.zip"
            if zip_path.exists():
                if st.button("Import Payroc Training Catalogue", type="primary"):
                    with st.spinner("Importing..."):
                        result = import_from_zip(str(zip_path))
                    success_message(f"Imported {result['new_containers']} containers")
                    st.rerun()
            else:
                st.caption("No ZIP file found in project folder.")
            return

        # Inject CSS
        st.markdown("""
        <style>
            .main > div.block-container {
                padding-top: 0 !important;
                margin-top: 0 !important;
            }
            section.main > div:first-child {
                padding-top: 0 !important;
            }
            a.anchor-link {
                display: none !important;
            }
            h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {
                display: none !important;
            }
            [data-testid="stDataFrame"] th:nth-child(1),
            [data-testid="stDataFrame"] td:nth-child(1) {
                min-width: 280px !important;
                max-width: 280px !important;
            }
            [data-testid="stDataFrame"] th:nth-child(2),
            [data-testid="stDataFrame"] td:nth-child(2) {
                min-width: 70px !important;
                max-width: 70px !important;
            }
            [data-testid="stDataFrame"] th:nth-child(3),
            [data-testid="stDataFrame"] td:nth-child(3) {
                min-width: 140px !important;
                max-width: 140px !important;
            }
            [data-testid="stDataFrame"] th:nth-child(4),
            [data-testid="stDataFrame"] td:nth-child(4) {
                min-width: 80px !important;
                max-width: 80px !important;
            }
            [data-testid="stDataFrame"] th:nth-child(5),
            [data-testid="stDataFrame"] td:nth-child(5) {
                min-width: 300px !important;
            }
        </style>
        """, unsafe_allow_html=True)

        # =========================================================================
        # Filter Bar (Department + Training Type + Audience) - MUST BE FIRST
        # Widgets update session state, then data fetch uses updated values
        # =========================================================================
        
        from services.scrub_rules import CANONICAL_AUDIENCES
        
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            # Department dropdown
            dept_options = ["All Departments"] + departments
            dept_index = 0
            if st.session_state.inv_department and st.session_state.inv_department in departments:
                dept_index = departments.index(st.session_state.inv_department) + 1
            
            selected_dept = st.selectbox(
                "Department",
                dept_options,
                index=dept_index,
                key="inv_dept_select"
            )
            
            if selected_dept == "All Departments":
                st.session_state.inv_department = None
            else:
                st.session_state.inv_department = selected_dept
        
        with col2:
            # Training Type dropdown (filtered by department if selected)
            training_types = get_active_training_types(st.session_state.inv_department)
            
            tt_options = ["All Types"] + training_types
            tt_index = 0
            if st.session_state.inv_training_type and st.session_state.inv_training_type in training_types:
                tt_index = training_types.index(st.session_state.inv_training_type) + 1
            elif st.session_state.inv_training_type and st.session_state.inv_training_type not in training_types:
                st.session_state.inv_training_type = None
            
            selected_tt = st.selectbox(
                "Training Type",
                tt_options,
                index=tt_index,
                format_func=lambda x: x if x == "All Types" else _get_training_type_label(x),
                key="inv_tt_select"
            )
            
            if selected_tt == "All Types":
                st.session_state.inv_training_type = None
            else:
                st.session_state.inv_training_type = selected_tt

        with col3:
            # Sales Stage filter - All / Untagged / specific stages
            stage_options = ["All", "Untagged"] + [k for k, _ in SALES_STAGES]
            stage_index = 0
            if st.session_state.inv_sales_stage == "untagged":
                stage_index = 1
            elif st.session_state.inv_sales_stage and st.session_state.inv_sales_stage in [k for k, _ in SALES_STAGES]:
                stage_index = stage_options.index(st.session_state.inv_sales_stage)
            
            def format_stage(x):
                if x == "All":
                    return "All"
                if x == "Untagged":
                    return "Untagged"
                return SALES_STAGE_LABELS.get(x, x)
            
            selected_stage = st.selectbox(
                "Sales Stage",
                stage_options,
                index=stage_index,
                format_func=format_stage,
                key="inv_stage_select"
            )
            
            if selected_stage == "All":
                st.session_state.inv_sales_stage = None
            elif selected_stage == "Untagged":
                st.session_state.inv_sales_stage = "untagged"
            else:
                st.session_state.inv_sales_stage = selected_stage

        with col4:
            # Audience filter (applied client-side after DB fetch)
            filter_options = ["All", "Unassigned"] + CANONICAL_AUDIENCES
            audience_filter = st.selectbox(
                "Audience",
                filter_options,
                index=0,
                key="audience_filter"
            )

        # =========================================================================
        # Fetch filtered containers (DB-backed) - AFTER filter widgets update state
        # =========================================================================
        
        containers = get_active_containers_filtered(
            primary_department=st.session_state.inv_department,
            training_type=st.session_state.inv_training_type,
            sales_stage=st.session_state.inv_sales_stage
        )
        
        # Compute header counts from same filtered result
        # PRIMARY: Total resources = SUM(resource_count) - canonical KPI, unchanged
        total_resource_count = sum(c.get('resource_count', 0) for c in containers)
        
        # SECONDARY: Items inside folders = SUM(compute_file_count) - informational only
        from services.container_service import compute_file_count
        items_inside_folders = sum(compute_file_count(c) for c in containers)

        # =========================================================================
        # Header (after data fetch so counts are correct)
        # =========================================================================

        # Build filter description
        filter_parts = []
        if st.session_state.inv_department:
            filter_parts.append(st.session_state.inv_department)
        if st.session_state.inv_training_type:
            filter_parts.append(_get_training_type_label(st.session_state.inv_training_type))
        filter_str = " / ".join(filter_parts) if filter_parts else "All Resources"

        st.markdown(f"""
        <div style="margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <h3 style="margin: 0; font-weight: 600;">Total resources ({total_resource_count})</h3>
                <span style="background: #f0f2f6; padding: 4px 10px; border-radius: 4px; font-size: 14px; color: rgb(49, 51, 63);">{filter_str}</span>
            </div>
            <p style="margin: 4px 0 0 0; font-size: 13px; color: #666;">Items inside folders: {items_inside_folders}</p>
        </div>
        """, unsafe_allow_html=True)

        if containers:
            def norm(v):
                return (v or "").strip()
            
            table_data = []
            for record in containers:
                ctype = record['container_type']
                rel_path = record['relative_path']
                display_name = record['display_name']
                
                if ctype == 'folder':
                    type_label = "FOLDER"
                    name_label = display_name
                    parent_path = str(Path(rel_path).parent)
                    path_label = format_display_path(parent_path)
                elif ctype == 'link':
                    type_label = "LINK"
                    name_label = display_name
                    path_without_hash = rel_path.split('#')[0]
                    path_label = format_display_path(path_without_hash)
                else:
                    basename = os.path.basename(rel_path)
                    name_part, ext = os.path.splitext(basename)
                    type_label = ext[1:].upper() if ext else "FILE"
                    name_label = name_part
                    parent_path = str(Path(rel_path).parent)
                    path_label = format_display_path(parent_path)
                
                if ctype == 'folder' or type_label == 'ZIP':
                    contents_count = record.get('contents_count', 0) or 0
                    contents_str = str(contents_count)
                else:
                    contents_str = "Single File"
                
                current_audience = record.get('audience') or ""
                
                table_data.append({
                    "container_key": record['container_key'],
                    "Name": name_label,
                    "Type": type_label,
                    "Audience": current_audience,
                    "Contents": contents_str,
                    "Path": path_label
                })
            
            original_df = pd.DataFrame(table_data)
            
            if audience_filter == "Unassigned":
                display_df = original_df[original_df["Audience"] == ""].copy()
            elif audience_filter != "All":
                display_df = original_df[original_df["Audience"] == audience_filter].copy()
            else:
                display_df = original_df.copy()
            
            orig_map = {row["container_key"]: norm(row["Audience"]) for _, row in display_df.iterrows()}
            
            st.markdown("---")
            
            # Log table size for performance profiling
            db_logger.info(f"TABLE: inventory_rows={len(display_df)} cols={len(display_df.columns)}")
            
            edited_df = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True,
                key="inventory_table_v6",
                column_config={
                    "container_key": None,
                    "Name": st.column_config.TextColumn("Name", width=350, disabled=True),
                    "Type": st.column_config.TextColumn("Type", width=70, disabled=True),
                    "Audience": st.column_config.SelectboxColumn(
                        "Audience",
                        options=CANONICAL_AUDIENCES,
                        width=120
                    ),
                    "Contents": st.column_config.TextColumn("Contents", width=80, disabled=True),
                    "Path": st.column_config.TextColumn("Path", width=350, disabled=True),
                },
                column_order=["Name", "Type", "Audience", "Contents", "Path"]
            )
            
            changes = []
            for _, row in edited_df.iterrows():
                key = row["container_key"]
                new_val = norm(row["Audience"])
                old_val = orig_map.get(key, "")
                
                if new_val != old_val:
                    if not new_val:
                        with message_container:
                            st.error("Audience cannot be cleared in Inventory. Assign a value or use Scrubbing.")
                    else:
                        changes.append((key, new_val))
            
            if changes:
                for key, new_audience in changes:
                    update_audience_bulk([key], new_audience)
                st.rerun()

        else:
            empty_state(
                "No resources found.",
                "Adjust filters or sync content from the Tools page."
            )
    
    render_page_frame(
        title="Inventory",
        subtitle="Browse and filter training content",
        content_callable=_render_content
    )
