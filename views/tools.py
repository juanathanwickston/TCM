"""
Tools View
==========
Import and export utilities.
All content imports are EXPLICIT user actions (no auto-import on startup).
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from pathlib import Path

from db import get_all_containers, get_active_containers, clear_containers, get_resource_totals
from services.container_service import import_from_zip

from components.layout import section_divider, empty_state, success_message, error_message
from components.filter_bar import render_active_filter_pills
from components.kpi_card import render_kpi_row
from components.page_frame import render_page_frame


def render():
    """Main tools content."""
    
    def _render_content(message_container):
        render_active_filter_pills()

        # Import Section
        st.subheader("Import Content")
        
        with message_container:
            st.warning("Content imports are explicit actions. The app does NOT auto-import on startup.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Import from ZIP**")
            
            uploaded = st.file_uploader("Upload training ZIP", type=['zip'], key="tools_zip_upload")
            
            if uploaded:
                if st.button("Process ZIP", type="primary", key="tools_process_zip"):
                    temp_path = Path(__file__).parent.parent / f"temp_{uploaded.name}"
                    with open(temp_path, 'wb') as f:
                        f.write(uploaded.getvalue())
                    
                    with st.spinner("Importing training resources..."):
                        result = import_from_zip(str(temp_path))
                    
                    temp_path.unlink(missing_ok=True)
                    
                    if result.get('errors'):
                        with message_container:
                            for err in result['errors'][:5]:
                                st.warning(err)
                    
                    success_message(f"Imported: {result['new_containers']} new, {result['updated_containers']} updated, {result['skipped']} skipped")
                    st.rerun()
            
            # Quick import for Payroc
            payroc_zip = Path(__file__).parent.parent / "Payroc Training Catalogue.zip"
            if payroc_zip.exists():
                st.markdown("---")
                st.markdown("**Quick Import: Payroc Training Catalogue**")
                if st.button("Import Payroc ZIP", key="tools_import_payroc"):
                    with st.spinner("Importing..."):
                        result = import_from_zip(str(payroc_zip))
                    success_message(f"Imported {result['new_containers']} new items")
                    st.rerun()

        with col2:
            st.markdown("**Sync Local Folder**")
            with message_container:
                st.info("Sync from `Payroc Training Catalogue/` folder (temporary SharePoint).")
            
            local_folder = Path(__file__).parent.parent / "Payroc Training Catalogue"
            
            if local_folder.exists() and local_folder.is_dir():
                st.caption(f"Folder found: `{local_folder.name}/`")
                if st.button("Sync Local Folder", type="primary", key="tools_sync_folder"):
                    with st.spinner("Syncing from local folder..."):
                        from services.container_service import import_from_folder
                        result = import_from_folder(str(local_folder))
                    
                    if result.get('errors'):
                        with message_container:
                            for err in result['errors'][:5]:
                                st.warning(err)
                    
                    success_message(
                        f"Synced: {result['new_containers']} new, "
                        f"{result['updated_containers']} updated, "
                        f"{result['skipped']} skipped"
                    )
                    st.rerun()
            else:
                with message_container:
                    st.error("Folder not found: `Payroc Training Catalogue/`")
                st.caption("Create this folder in the project root to enable local sync.")

        section_divider()

        # Export Section
        st.subheader("Export Data")
        
        containers = get_all_containers()
        
        if containers:
            df = pd.DataFrame(containers)
            
            cols = [
                'display_name', 'relative_path', 'container_type', 'bucket',
                'primary_department', 'training_type', 'resource_count',
                'valid_link_count', 'is_placeholder',
                'scrub_status', 'scrub_owner', 'scrub_notes',
                'invest_decision', 'invest_owner', 'invest_effort', 'invest_notes',
                'first_seen', 'last_seen', 'source'
            ]
            export_df = df[[c for c in cols if c in df.columns]]
            
            st.caption(f"{len(export_df):,} records total")
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.download_button(
                    "Download CSV",
                    data=export_df.to_csv(index=False),
                    file_name="training_resources_export.csv",
                    mime="text/csv",
                    key="tools_download_csv"
                )
            
            with c2:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    export_df.to_excel(writer, sheet_name='Resources', index=False)
                output.seek(0)
                st.download_button(
                    "Download Excel",
                    data=output,
                    file_name="training_resources_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="tools_download_excel"
                )
        else:
            empty_state("No data to export.", "Import content first.")

        section_divider()

        # Statistics
        st.subheader("Resource Statistics")
        
        active_containers = get_active_containers()
        
        if active_containers:
            totals = get_resource_totals()
            
            render_kpi_row([
                {"label": "Onboarding", "value": str(totals['onboarding'])},
                {"label": "Upskilling", "value": str(totals['upskilling'])},
                {"label": "Not Sure", "value": str(totals['not_sure'])},
                {"label": "Records", "value": str(totals['total_containers'])},
                {"label": "Invest Queue", "value": str(totals['investment_queue'])},
            ])
            
            st.markdown("---")
            st.markdown("**Department Breakdown** (excludes Not Sure)")
            
            if totals['dept_breakdown']:
                for dept, count in sorted(totals['dept_breakdown'].items()):
                    st.markdown(f"- **{dept.replace('_', ' ').title()}:** {count} resources")
            else:
                st.caption("No department data available")

        section_divider()

        # Maintenance
        st.subheader("Maintenance")
        
        st.markdown("**Audience Migration**")
        st.caption("Backfill audience from existing primary_department values when they match audience categories. Safe to run multiple times.")
        if st.button("Run Audience Migration", key="tools_run_migration"):
            from db import run_audience_migration
            with st.spinner("Running migration..."):
                result = run_audience_migration()
            
            if result['diagnostics']:
                st.markdown("**Values found in primary_department (pre-migration):**")
                for val, cnt in result['diagnostics'][:10]:
                    st.caption(f"  • `{val}`: {cnt} rows")
            
            success_message(
                f"Backfilled: {result['backfilled']} rows. "
                f"Cleaned up: {result['cleaned_up']} snake_case values. "
                f"Remaining unassigned: {result['remaining_null']}."
            )
            st.rerun()

        st.markdown("---")
        with message_container:
            st.warning("Use with caution")

        with st.expander("Danger Zone"):
            st.markdown("**Clear All Data**")
            st.caption("This will delete all data. Scrub/invest decisions will be lost.")
            
            if st.button("Clear All Data", type="secondary", key="tools_clear_data"):
                confirm = st.checkbox("I understand this cannot be undone", key="tools_confirm_clear")
                if confirm:
                    clear_containers()
                    success_message("All data cleared")
                    st.rerun()
    
    render_page_frame(
        title="Tools",
        subtitle="Import, export, and maintenance utilities",
        content_callable=_render_content,
        footer_text="Stage 4 | Training Catalogue Manager"
    )
