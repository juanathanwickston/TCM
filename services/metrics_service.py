"""
Metrics service: KPI calculations and chart aggregations.
Used by Dashboard to compute executive metrics.
"""

from typing import Dict, Any, List, Optional
import pandas as pd

from services.catalog_service import get_all_items
from models.enums import ScrubStatus


def get_catalog_stats(department_filter: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Calculate catalog statistics for dashboard KPIs.
    Optionally filtered by department list.
    """
    items = get_all_items()
    
    if not items:
        return _empty_stats()
    
    df = pd.DataFrame(items)
    all_departments = sorted(df['department'].unique().tolist())
    
    # Apply department filter
    if department_filter:
        df = df[df['department'].isin(department_filter)]
    
    if df.empty:
        stats = _empty_stats()
        stats['departments'] = all_departments
        return stats
    
    total = len(df)
    
    # Scrubbing progress
    not_reviewed = len(df[df['scrub_status'].isin([None, '', ScrubStatus.NOT_REVIEWED.value])])
    reviewed = total - not_reviewed
    scrubbing_pct = (reviewed / total * 100) if total > 0 else 0
    
    # Status counts
    status_counts = {
        'not_reviewed': not_reviewed,
        'keep': len(df[df['scrub_status'] == ScrubStatus.KEEP.value]),
        'modify': len(df[df['scrub_status'] == ScrubStatus.MODIFY.value]),
        'sunset': len(df[df['scrub_status'] == ScrubStatus.SUNSET.value]),
        'gap': len(df[df['scrub_status'] == ScrubStatus.GAP.value]),
    }
    
    return {
        'total_items': total,
        'total_files': len(df[df['item_type'] == 'file']),
        'total_links': len(df[df['item_type'] == 'link']),
        'onboarding_items': len(df[df['bucket'] == 'Onboarding']),
        'upskilling_items': len(df[df['bucket'] == 'Upskilling']),
        'scrubbing_pct': scrubbing_pct,
        'investment_queue': status_counts['modify'] + status_counts['gap'],
        'status_counts': status_counts,
        'departments': all_departments,
        'training_types': df['training_type'].value_counts().to_dict(),
    }


def _empty_stats() -> Dict[str, Any]:
    """Return empty stats structure."""
    return {
        'total_items': 0,
        'total_files': 0,
        'total_links': 0,
        'onboarding_items': 0,
        'upskilling_items': 0,
        'scrubbing_pct': 0,
        'investment_queue': 0,
        'status_counts': {
            'not_reviewed': 0, 'keep': 0, 'modify': 0, 'sunset': 0, 'gap': 0
        },
        'departments': [],
        'training_types': {},
    }
