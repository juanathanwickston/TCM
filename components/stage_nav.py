"""
Stage navigation component.
Clickable tiles that navigate to stage pages using Streamlit native routing.
"""

import streamlit as st
from typing import Dict, Any
from components.ux_contract import StageState, STAGE_COLORS


def get_stage_state(
    is_complete: bool = False,
    is_started: bool = False,
    needs_attention: bool = False
) -> StageState:
    """Determine stage state from conditions."""
    if needs_attention:
        return StageState.NEEDS_ATTENTION
    if is_complete:
        return StageState.COMPLETE
    if is_started:
        return StageState.IN_PROGRESS
    return StageState.NOT_STARTED


def render_stage_tiles(stages: list) -> None:
    """
    Render clickable stage navigation tiles.
    
    Args:
        stages: List of dicts with keys:
            - name: Display name
            - page: Page file path (e.g., "pages/1_Initial_Inventory.py")
            - state: StageState enum
            - subtitle: Optional subtitle text
    """
    cols = st.columns(len(stages))
    
    for col, stage in zip(cols, stages):
        with col:
            state = stage.get("state", StageState.NOT_STARTED)
            color = STAGE_COLORS.get(state, STAGE_COLORS[StageState.NOT_STARTED])
            
            # State indicator
            if state == StageState.COMPLETE:
                indicator = "[Complete]"
            elif state == StageState.IN_PROGRESS:
                indicator = "[In Progress]"
            elif state == StageState.NEEDS_ATTENTION:
                indicator = "[Needs Attention]"
            else:
                indicator = "[Not Started]"
            
            # Render as button that navigates
            if st.button(
                f"{stage['name']}\n{indicator}",
                key=f"stage_{stage['name']}",
                use_container_width=True
            ):
                st.switch_page(stage["page"])
            
            if stage.get("subtitle"):
                st.caption(stage["subtitle"])
