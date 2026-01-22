"""
Dashboard View
==============
Executive Dashboard - Decision instrument for executives.
Answers: Where are we exposed? What is blocking value? What must be decided next?
"""

import streamlit as st

from services.kpi_service import (
    get_submission_summary,
    get_scrub_status_breakdown,
    get_source_breakdown,
    get_training_type_breakdown,
    get_duplicate_count,
)
from db import get_sales_stage_breakdown
from components.layout import section_header, section_divider
from components.page_frame import render_page_frame


def render():
    """Main dashboard content."""
    
    def _render_content(message_container):
        # Dashboard-only KPI styling
        st.markdown("""
        <style>
            .kpi-large {
                font-size: 3rem;
                font-weight: 700;
                line-height: 1.1;
                margin: 0;
            }
            .kpi-label {
                font-size: 0.875rem;
                color: #6b7280;
                margin-top: 4px;
            }
            .coverage-gap { color: #dc2626; }
            .coverage-ok { color: #16a34a; }
        </style>
        """, unsafe_allow_html=True)
        
        # =============================================================================
        # SECTION 1: SUBMISSION OVERVIEW
        # =============================================================================

        section_header("Submission Overview")
        
        summary = get_submission_summary()
        status = get_scrub_status_breakdown()
        
        # Compute KPI #2: Total content items from same dataset as KPI #1
        from db import get_active_containers
        from services.container_service import compute_file_count
        active_containers = get_active_containers()
        # Filter same as KPI service: is_archived=0, is_placeholder=0
        filtered_containers = [c for c in active_containers if not c.get('is_placeholder')]
        total_content_items = sum(compute_file_count(c) for c in filtered_containers)
        
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            st.markdown(f'<p class="kpi-large">{summary["total"]:,}</p>', unsafe_allow_html=True)
            st.markdown('<p class="kpi-label">Total Submissions</p>', unsafe_allow_html=True)
        
        with c2:
            st.markdown(f'<p class="kpi-large">{total_content_items:,}</p>', unsafe_allow_html=True)
            st.markdown('<p class="kpi-label">Total content items</p>', unsafe_allow_html=True)
        
        with c3:
            st.markdown(f'<p class="kpi-large">{status["unreviewed"]:,}</p>', unsafe_allow_html=True)
            st.markdown('<p class="kpi-label">Items Remaining</p>', unsafe_allow_html=True)
        
        with c4:
            dupes = get_duplicate_count()
            st.markdown(f'<p class="kpi-large">{dupes:,}</p>', unsafe_allow_html=True)
            st.markdown('<p class="kpi-label">Duplicates</p>', unsafe_allow_html=True)
            st.caption("Coming soon")
        
        section_divider()
        
        # Breakdown
        section_header("Breakdown")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("Onboarding vs Upskilling")
            total = summary['total'] or 1
            st.markdown(f"""
- **Onboarding**: {summary['onboarding']:,} ({summary['onboarding']/total*100:.0f}%)
- **Upskilling**: {summary['upskilling']:,} ({summary['upskilling']/total*100:.0f}%)
- **Other**: {summary['other']:,} ({summary['other']/total*100:.0f}%)
            """)
        
        with c2:
            st.subheader("Include vs Modify vs Sunset")
            st.markdown(f"""
- **Include**: {status['include']:,}
- **Modify**: {status['modify']:,}
- **Sunset**: {status['sunset']:,}
            """)
        
        section_divider()
        
        # Sources table
        section_header("Training Sources")
        st.caption("Where did the training come from?")
        sources = get_source_breakdown()
        if sources:
            st.table([{"Source": s['source'], "Count": f"{s['count']:,}", "% of Total": f"{s['pct']:.0f}%"} for s in sources[:10]])
        else:
            with message_container:
                st.info("No source data available.")
        
        section_divider()
        
        # Training types table
        section_header("Training Types")
        st.caption("What type of training was collected?")
        types = get_training_type_breakdown()
        if types:
            def format_type(t):
                return t.replace('_', ' ').title() if t else 'Unknown'
            st.table([{"Type": format_type(t['type']), "Count": f"{t['count']:,}", "% of Total": f"{t['pct']:.0f}%"} for t in types[:10]])
        else:
            with message_container:
                st.info("No training type data available.")
        
        section_divider()
        
        # Sales-Tagged Content by Stage
        section_header("Sales-Tagged Content by Stage")
        st.caption("Only includes content where a Sales Stage has been assigned.")
        stages = get_sales_stage_breakdown()
        if stages:
            st.table([{"Stage": s['label'], "Resources": f"{s['count']:,}"} for s in stages])
        else:
            with message_container:
                st.info("No sales-tagged content yet. Assign Sales Stage during Scrubbing.")
    
    render_page_frame(
        title="Dashboard",
        subtitle="Training catalog overview and metrics",
        content_callable=_render_content
    )
