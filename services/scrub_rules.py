"""
Scrub Rules
===========
Single source of truth for scrub decisions, reasons, and field whitelist.
"""

from typing import Dict, Any, Optional

# =============================================================================
# CANONICAL SCRUB STATUSES (Locked)
# =============================================================================

# What Scrubbing UI is allowed to WRITE (canonical only)
CANONICAL_SCRUB_STATUSES = ('Include', 'Modify', 'Sunset')

# Valid scrub decisions - CANONICAL ONLY (migration normalizes legacy values)
VALID_SCRUB_DECISIONS = frozenset({
    'not_reviewed',
    'Include', 'Modify', 'Sunset',
})


def normalize_status(raw: Optional[str]) -> str:
    """
    Map any stored status to canonical display value.
    
    Returns one of: 'Unreviewed', 'Include', 'Modify', 'Sunset', 'LegacyUnknown'
    """
    if raw is None or raw == '' or raw == 'not_reviewed':
        return 'Unreviewed'
    mapping = {
        'PASS': 'Include', 'Include': 'Include',
        'HOLD': 'Modify', 'Modify': 'Modify', 'modify': 'Modify', 'gap': 'Modify',
        'BLOCK': 'Sunset', 'Sunset': 'Sunset',
    }
    return mapping.get(raw, 'LegacyUnknown')


# Valid scrub reasons - kept for backwards compatibility
VALID_SCRUB_REASONS = frozenset({
    'incomplete',
    'outdated',
    'wrong_audience',
    'duplicate',
    'unclear_intent',
    'compliance_risk',
})

# Display labels for reasons in UI
REASON_LABELS = {
    'incomplete': 'Incomplete',
    'outdated': 'Outdated',
    'wrong_audience': 'Wrong Audience',
    'duplicate': 'Duplicate',
    'unclear_intent': 'Unclear Intent',
    'compliance_risk': 'Compliance Risk',
}

# Field whitelist for batch updates (extended with scrub_reasons)
SCRUB_FIELD_WHITELIST = frozenset({
    'scrub_status',
    'scrub_owner',
    'scrub_notes',
    'scrub_reasons',
    'audience',
})

# =============================================================================
# CANONICAL AUDIENCES (Locked - Single Source of Truth)
# =============================================================================
# This list is AUTHORITATIVE. No aliases, no substitutions, no additions
# without explicit approval. Case-sensitive and exact.

CANONICAL_AUDIENCES = [
    'Direct Sales',
    'Indirect Sales',
    'Integration',
    'FI',
    'Partner Management',
    'Operations',
    'Compliance',
    'POS',
]


def is_reviewed(container: Dict[str, Any]) -> bool:
    """Check if container has been reviewed (has a decision)."""
    normalized = normalize_status(container.get('scrub_status'))
    return normalized in {'Include', 'Modify', 'Sunset'}


def is_complete(container: Dict[str, Any]) -> bool:
    """
    Check if scrubbing is complete for a container.
    Complete = reviewed + has audience + has owner
    """
    if not is_reviewed(container):
        return False
    if not container.get('audience'):
        return False
    if not container.get('scrub_owner'):
        return False
    return True


def has_value(val: Any) -> bool:
    """Check if a value is non-empty."""
    if val is None:
        return False
    if isinstance(val, str) and val.strip() == '':
        return False
    return True


def get_completion_breakdown(containers: list) -> dict:
    """Get breakdown of completion status."""
    total = len(containers)
    complete = sum(1 for c in containers if is_complete(c))
    missing_status = sum(1 for c in containers if not is_reviewed(c))
    missing_audience = sum(1 for c in containers if not has_value(c.get('audience')))
    missing_owner = sum(1 for c in containers if not has_value(c.get('scrub_owner')))
    
    return {
        'total': total,
        'complete': complete,
        'missing_status': missing_status,
        'missing_audience': missing_audience,
        'missing_owner': missing_owner,
        'missing_notes': 0,  # Notes are now optional for all
        'invalid_status': 0,  # No invalid statuses after migration
    }
