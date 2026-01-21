"""
Investment View
===============
Build/Buy/Assign decisions for modify/gap containers.
"""

import streamlit as st

from db import get_containers_by_scrub_status, update_container_invest
from models.enums import ScrubStatus, InvestDecision

from components.layout import page_header, section_divider, page_footer, empty_state, success_message
from components.filter_bar import render_active_filter_pills, get_active_filters
from components.kpi_card import render_kpi_row
from components.status_chip import get_scrub_label, get_invest_label


def render():
    """Main investment content."""
    
    page_header("Investment Planning", "Plan build/buy/assign decisions")
    render_active_filter_pills()

    containers = get_containers_by_scrub_status(['modify', 'gap'])
    
    if not containers:
        empty_state("No containers require investment.", "Complete Scrubbing to identify items marked as Modify or Gap.")
        page_footer("Stage 3 | Training Catalogue Manager")
        return

    # Apply global filter
    filters = get_active_filters()
    if filters.get("departments"):
        containers = [c for c in containers if c.get('primary_department') in filters["departments"]]

    if not containers:
        empty_state("No containers match your filters.", "Clear filters to see all.")
        page_footer("Stage 3 | Training Catalogue Manager")
        return

    # Summary
    st.subheader("Investment Queue Summary")
    
    modify_count = len([c for c in containers if c.get('scrub_status') == 'modify'])
    gap_count = len([c for c in containers if c.get('scrub_status') == 'gap'])
    decided_count = len([c for c in containers if c.get('invest_decision')])
    
    render_kpi_row([
        {"label": "Total", "value": str(len(containers))},
        {"label": "Modify", "value": str(modify_count)},
        {"label": "Gap", "value": str(gap_count)},
        {"label": "Decided", "value": str(decided_count)},
    ])
    
    section_divider()

    # Local Filters
    st.subheader("Filters")
    f1, f2 = st.columns(2)
    filter_scrub = f1.selectbox("Scrub Status", ["All", "modify", "gap"], key="invest_scrub_filter")
    filter_decision = f2.selectbox("Decision", ["All", "pending", "build", "buy", "assign_sme", "defer"], key="invest_decision_filter")
    
    filtered = containers
    if filter_scrub != "All":
        filtered = [c for c in filtered if c.get('scrub_status') == filter_scrub]
    if filter_decision != "All":
        if filter_decision == "pending":
            filtered = [c for c in filtered if not c.get('invest_decision')]
        else:
            filtered = [c for c in filtered if c.get('invest_decision') == filter_decision]
    
    st.caption(f"Showing {len(filtered)} containers")
    section_divider()

    # Container List
    st.subheader("Decisions")
    
    scrub_labels = ScrubStatus.display_labels()
    invest_labels = InvestDecision.display_labels()
    
    for container in filtered:
        current = container.get('invest_decision') or ""
        scrub = get_scrub_label(container.get('scrub_status'))
        dec = get_invest_label(current) if current else "Pending"
        
        with st.expander(f"{container['display_name']} | {scrub} | {dec}"):
            st.markdown(f"**Dept:** {container.get('primary_department') or 'N/A'} | **Type:** {container.get('training_type') or 'N/A'}")
            st.markdown(f"**Path:** `{container['relative_path']}`")
            if container.get('scrub_notes'):
                st.markdown(f"**Scrub Notes:** {container['scrub_notes']}")
            section_divider()
            
            c1, c2 = st.columns(2)
            
            with c1:
                choices = [""] + InvestDecision.choices()
                idx = choices.index(current) if current in choices else 0
                decision = st.selectbox(
                    "Decision *", choices,
                    format_func=lambda x: invest_labels.get(x, "Select...") if x else "Select...",
                    index=idx,
                    key=f"d_{container['container_key']}"
                )
                owner = st.text_input(
                    "Owner *",
                    value=container.get('invest_owner') or "",
                    key=f"o_{container['container_key']}"
                )
            
            with c2:
                effort_required = decision in ['build', 'buy', 'assign_sme']
                effort_label = "Cost *" if decision == 'buy' else "Effort *" if effort_required else "Effort"
                effort = st.text_input(
                    effort_label,
                    value=container.get('invest_effort') or "",
                    placeholder="e.g., 2 weeks or $5,000",
                    key=f"e_{container['container_key']}"
                )
                
                notes_required = decision == 'defer'
                notes = st.text_area(
                    "Notes" + (" * (why/when)" if notes_required else ""),
                    value=container.get('invest_notes') or "",
                    key=f"n_{container['container_key']}"
                )
            
            if st.button("Save", key=f"b_{container['container_key']}", type="primary"):
                errors = []
                if not decision:
                    errors.append("Decision required")
                if not owner.strip():
                    errors.append("Owner required")
                if effort_required and not effort.strip():
                    errors.append(f"{effort_label.replace(' *', '')} required")
                if notes_required and not notes.strip():
                    errors.append("Notes required for defer")
                
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    with st.spinner("Saving..."):
                        update_container_invest(
                            container['container_key'],
                            decision,
                            owner.strip(),
                            effort.strip() if effort else None,
                            notes.strip() if notes else None
                        )
                    success_message("Saved")
                    st.rerun()

    page_footer("Stage 3 | Training Catalogue Manager")
