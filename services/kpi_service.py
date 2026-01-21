"""
KPI Service — Executive Dashboard Metrics
==========================================
Centralized SQL queries for all executive KPIs.

All queries use the canonical predicate:
    WHERE is_archived = 0 AND is_placeholder = 0

This module is the single source of truth for dashboard metrics.
Do not compute KPIs in the UI layer.
"""

from typing import Dict, List, Any, Optional
from db import get_connection


# =============================================================================
# BASE: Total Active Resources (denominator for all percentages)
# =============================================================================

def get_total_active_resources() -> int:
    """Total resource_count for active, non-placeholder containers."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(SUM(resource_count), 0) AS total
        FROM resource_containers
        WHERE is_archived = 0 AND is_placeholder = 0
    """)
    result = cursor.fetchone()['total']
    conn.close()
    return result


# =============================================================================
# TIER-1 KPIs
# =============================================================================

def get_catalog_trust_score() -> Dict[str, Any]:
    """
    Catalog Trust Score (%)
    
    Trusted = Decisioned (keep/modify/sunset/gap) AND Audience assigned
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        totals AS (
            SELECT COALESCE(SUM(resource_count), 0) AS total_resources FROM active
        ),
        trusted AS (
            SELECT COALESCE(SUM(resource_count), 0) AS trusted_resources
            FROM active
            WHERE scrub_status IN ('keep', 'modify', 'sunset', 'gap')
              AND audience IS NOT NULL AND TRIM(audience) <> ''
        )
        SELECT
            trusted.trusted_resources,
            totals.total_resources,
            CASE WHEN totals.total_resources = 0 THEN 0.0
                 ELSE ROUND(100.0 * trusted.trusted_resources / totals.total_resources, 1)
            END AS pct
        FROM trusted, totals
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'trusted_resources': row['trusted_resources'],
        'total_resources': row['total_resources'],
        'pct': row['pct'],
    }


def get_unreviewed_exposure() -> int:
    """
    Unreviewed Exposure
    
    Total resource_count for containers not yet reviewed.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COALESCE(SUM(resource_count), 0) AS unreviewed_exposure
        FROM resource_containers
        WHERE is_archived = 0 AND is_placeholder = 0
          AND (scrub_status IS NULL OR TRIM(scrub_status) = '' OR scrub_status = 'not_reviewed')
    """)
    
    result = cursor.fetchone()['unreviewed_exposure']
    conn.close()
    return result


def get_incomplete_resources() -> Dict[str, Any]:
    """
    Incomplete Resources
    
    Total resource_count for containers that are not complete.
    Complete = reviewed + audience + owner + notes (if sunset/gap)
    
    Uses scrub_rules for consistent definitions.
    """
    from services.scrub_rules import is_complete, get_completion_breakdown
    from db import get_active_containers
    
    containers = get_active_containers()
    breakdown = get_completion_breakdown(containers)
    
    # Calculate incomplete resource count (not container count)
    incomplete_count = 0
    for c in containers:
        if not is_complete(c):
            incomplete_count += c.get('resource_count', 1)
    
    return {
        'incomplete': incomplete_count,
        'total': sum(c.get('resource_count', 1) for c in containers),
        'breakdown': breakdown
    }


def get_decision_latency_days() -> Optional[int]:
    """
    Decision Latency (Days)
    
    Median age (days since first_seen) of containers not decisioned.
    Returns None if no pending containers.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        pending AS (
            SELECT
                container_key,
                CAST((julianday('now') - julianday(first_seen)) AS INTEGER) AS age_days
            FROM active
            WHERE scrub_status IS NULL
               OR TRIM(scrub_status) = ''
               OR scrub_status = 'not_reviewed'
        ),
        ordered AS (
            SELECT
                age_days,
                ROW_NUMBER() OVER (ORDER BY age_days) AS rn,
                COUNT(*) OVER () AS cnt
            FROM pending
        )
        SELECT
            CASE
                WHEN cnt = 0 THEN NULL
                WHEN cnt % 2 = 1 THEN (SELECT age_days FROM ordered WHERE rn = (cnt + 1)/2)
                ELSE (
                    (SELECT age_days FROM ordered WHERE rn = cnt/2) +
                    (SELECT age_days FROM ordered WHERE rn = cnt/2 + 1)
                ) / 2
            END AS median_days
        FROM ordered
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        return None
    return row['median_days']


# =============================================================================
# TIER-2 KPIs
# =============================================================================

def get_audience_coverage() -> Dict[str, Any]:
    """
    Audience Coverage (%)
    
    Percentage of resources with a non-NULL, non-blank audience.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        totals AS (
            SELECT COALESCE(SUM(resource_count), 0) AS total_resources FROM active
        ),
        assigned AS (
            SELECT COALESCE(SUM(resource_count), 0) AS assigned_resources
            FROM active
            WHERE audience IS NOT NULL AND TRIM(audience) <> ''
        )
        SELECT
            assigned.assigned_resources,
            totals.total_resources,
            CASE WHEN totals.total_resources = 0 THEN 0.0
                 ELSE ROUND(100.0 * assigned.assigned_resources / totals.total_resources, 1)
            END AS pct
        FROM assigned, totals
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'assigned_resources': row['assigned_resources'],
        'total_resources': row['total_resources'],
        'pct': row['pct'],
    }


def get_audience_coverage_gaps() -> List[Dict[str, Any]]:
    """
    Audience Coverage Gaps
    
    Returns list of canonical audiences with their assigned count and status.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        canon(audience) AS (
            VALUES
                ('Direct'),('Indirect'),('FI'),
                ('Partner Management'),('Operations'),
                ('Compliance'),('Integration'),('POS')
        ),
        counts AS (
            SELECT
                audience,
                COALESCE(SUM(resource_count), 0) AS assigned_resources
            FROM active
            WHERE audience IS NOT NULL AND TRIM(audience) <> ''
            GROUP BY audience
        )
        SELECT
            canon.audience,
            COALESCE(counts.assigned_resources, 0) AS assigned_resources,
            CASE WHEN COALESCE(counts.assigned_resources, 0) = 0 THEN 'NO_COVERAGE'
                 ELSE 'COVERED'
            END AS status
        FROM canon
        LEFT JOIN counts ON counts.audience = canon.audience
        ORDER BY assigned_resources ASC, canon.audience ASC
    """)
    
    results = [
        {
            'audience': row['audience'],
            'assigned_resources': row['assigned_resources'],
            'status': row['status'],
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return results


def get_investment_ready_inventory() -> Dict[str, int]:
    """
    Investment-Ready Inventory
    
    Containers where scrub_status='keep' AND valid department AND audience assigned.
    Valid department = exists in departments table (discovered from folder structure).
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        valid_depts AS (
            SELECT department FROM departments
        )
        SELECT
            COUNT(*) AS containers,
            COALESCE(SUM(resource_count), 0) AS resources
        FROM active
        WHERE scrub_status = 'keep'
          AND audience IS NOT NULL AND TRIM(audience) <> ''
          AND primary_department IN (SELECT department FROM valid_depts)
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'containers': row['containers'],
        'resources': row['resources'],
    }


# =============================================================================
# PRIORITY QUEUES
# =============================================================================

def get_largest_unreviewed_buckets(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Largest Unreviewed Buckets
    
    Ranked by total resources, with days since oldest resource entered.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        unrev AS (
            SELECT * FROM active
            WHERE scrub_status IS NULL
               OR TRIM(scrub_status) = ''
               OR scrub_status = 'not_reviewed'
        )
        SELECT
            bucket,
            COALESCE(SUM(resource_count), 0) AS total_resources,
            CAST(MAX(julianday('now') - julianday(first_seen)) AS INTEGER) AS days_since_oldest
        FROM unrev
        WHERE bucket IS NOT NULL
        GROUP BY bucket
        ORDER BY total_resources DESC
        LIMIT ?
    """, (limit,))
    
    results = [
        {
            'bucket': row['bucket'],
            'total_resources': row['total_resources'],
            'days_since_oldest': row['days_since_oldest'],
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return results


def get_top_investment_ready_resources(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Top Investment-Ready Resources
    
    Ranked by resource_count.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        valid_depts AS (
            SELECT department FROM departments
        )
        SELECT
            display_name AS name,
            audience,
            primary_department AS department,
            resource_count
        FROM active
        WHERE scrub_status = 'keep'
          AND audience IS NOT NULL AND TRIM(audience) <> ''
          AND primary_department IN (SELECT department FROM valid_depts)
        ORDER BY resource_count DESC, display_name ASC
        LIMIT ?
    """, (limit,))
    
    results = [
        {
            'name': row['name'],
            'audience': row['audience'],
            'department': row['department'],
            'resource_count': row['resource_count'],
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return results


# =============================================================================
# SUPPORTING METRICS
# =============================================================================

def get_resources_reviewed() -> Dict[str, Any]:
    """
    Resources Reviewed (%)
    
    Reviewed = scrub_status is set and not 'not_reviewed'.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        totals AS (
            SELECT COALESCE(SUM(resource_count), 0) AS total_resources FROM active
        ),
        reviewed AS (
            SELECT COALESCE(SUM(resource_count), 0) AS reviewed_resources
            FROM active
            WHERE scrub_status IS NOT NULL
              AND TRIM(scrub_status) <> ''
              AND scrub_status <> 'not_reviewed'
        )
        SELECT
            reviewed.reviewed_resources,
            totals.total_resources,
            CASE WHEN totals.total_resources = 0 THEN 0.0
                 ELSE ROUND(100.0 * reviewed.reviewed_resources / totals.total_resources, 1)
            END AS pct
        FROM reviewed, totals
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'reviewed_resources': row['reviewed_resources'],
        'total_resources': row['total_resources'],
        'pct': row['pct'],
    }


def get_resources_decisioned() -> Dict[str, Any]:
    """
    Resources Decisioned (%)
    
    Decisioned = keep | modify | sunset | gap
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH active AS (
            SELECT * FROM resource_containers
            WHERE is_archived = 0 AND is_placeholder = 0
        ),
        totals AS (
            SELECT COALESCE(SUM(resource_count), 0) AS total_resources FROM active
        ),
        decisioned AS (
            SELECT COALESCE(SUM(resource_count), 0) AS decisioned_resources
            FROM active
            WHERE scrub_status IN ('keep', 'modify', 'sunset', 'gap')
        )
        SELECT
            decisioned.decisioned_resources,
            totals.total_resources,
            CASE WHEN totals.total_resources = 0 THEN 0.0
                 ELSE ROUND(100.0 * decisioned.decisioned_resources / totals.total_resources, 1)
            END AS pct
        FROM decisioned, totals
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'decisioned_resources': row['decisioned_resources'],
        'total_resources': row['total_resources'],
        'pct': row['pct'],
    }


# =============================================================================
# LEADERSHIP METRICS (Presentation KPIs)
# =============================================================================

def get_submission_summary() -> Dict[str, Any]:
    """
    Leadership KPI: Total submissions and breakdown by bucket.
    
    Uses SUM(resource_count) for reconciliation with Inventory.
    Uses LOWER(TRIM(bucket)) for robust matching.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT
            COALESCE(SUM(resource_count), 0) AS total,
            COALESCE(SUM(CASE WHEN LOWER(TRIM(bucket)) = 'onboarding' THEN resource_count ELSE 0 END), 0) AS onboarding,
            COALESCE(SUM(CASE WHEN LOWER(TRIM(bucket)) = 'upskilling' THEN resource_count ELSE 0 END), 0) AS upskilling
        FROM resource_containers
        WHERE is_archived = 0 AND is_placeholder = 0
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    total = row['total'] or 0
    onboarding = row['onboarding'] or 0
    upskilling = row['upskilling'] or 0
    
    return {
        'total': total,
        'onboarding': onboarding,
        'upskilling': upskilling,
        'other': total - onboarding - upskilling
    }


def get_scrub_status_breakdown() -> Dict[str, Any]:
    """
    Leadership KPI: Status distribution using SUM(resource_count).
    
    Includes 'other' bucket for statuses not in canonical set.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COALESCE(SUM(resource_count), 0) as total,
            COALESCE(SUM(CASE WHEN scrub_status = 'Sunset' THEN resource_count ELSE 0 END), 0) as sunset,
            COALESCE(SUM(CASE WHEN scrub_status = 'Include' THEN resource_count ELSE 0 END), 0) as include,
            COALESCE(SUM(CASE WHEN scrub_status = 'Modify' THEN resource_count ELSE 0 END), 0) as modify,
            COALESCE(SUM(CASE WHEN scrub_status = 'not_reviewed' THEN resource_count ELSE 0 END), 0) as unreviewed
        FROM resource_containers
        WHERE is_archived = 0 AND is_placeholder = 0
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    total = row['total'] or 0
    sunset = row['sunset'] or 0
    include = row['include'] or 0
    modify = row['modify'] or 0
    unreviewed = row['unreviewed'] or 0
    
    # Other = anything not in the four canonical statuses
    other = total - (sunset + include + modify + unreviewed)
    
    return {
        'total': total,
        'remaining': total - sunset,
        'sunset': sunset,
        'include': include,
        'modify': modify,
        'unreviewed': unreviewed,
        'other': other
    }


def get_source_breakdown() -> List[Dict[str, Any]]:
    """
    Leadership KPI: Where did training come from?
    
    Uses SUM(resource_count) per primary_department.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COALESCE(primary_department, 'Unknown') as source,
            COALESCE(SUM(resource_count), 0) as count
        FROM resource_containers
        WHERE is_archived = 0 AND is_placeholder = 0
        GROUP BY primary_department
        ORDER BY count DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    total = sum(r['count'] for r in rows) or 1
    return [{'source': r['source'], 'count': r['count'], 'pct': r['count'] / total * 100} for r in rows]


def get_training_type_breakdown() -> List[Dict[str, Any]]:
    """
    Leadership KPI: What type of training was collected?
    
    Uses SUM(resource_count) per training_type.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COALESCE(training_type, 'Unknown') as type,
            COALESCE(SUM(resource_count), 0) as count
        FROM resource_containers
        WHERE is_archived = 0 AND is_placeholder = 0
        GROUP BY training_type
        ORDER BY count DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    total = sum(r['count'] for r in rows) or 1
    return [{'type': r['type'], 'count': r['count'], 'pct': r['count'] / total * 100} for r in rows]


def get_duplicate_count() -> int:
    """
    Leadership KPI: Duplicate submissions.
    
    Placeholder for demo — returns 0.
    """
    return 0
