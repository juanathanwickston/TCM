"""
Signal Service
==============
Deterministic signal computation for machine-assisted scrubbing.
No ML, no confidence scores, no content parsing.
"""

from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta


# Risk keywords that suggest HOLD + outdated
RISK_KEYWORDS = {'draft', 'old', 'v1', 'v2', 'test', 'temp', 'backup', 'copy'}

# Compliance keywords that suggest HOLD + compliance_risk
COMPLIANCE_KEYWORDS = {'compliance', 'legal', 'policy', 'hipaa', 'pci', 'gdpr'}

# Generic filenames that suggest low information
GENERIC_NAMES = {'readme', 'index', 'main', 'document', 'file', 'untitled', 'new'}


def compute_duplicate_map(containers: List[dict]) -> Dict[str, int]:
    """
    Build a map of display_name -> count of distinct relative_paths.
    One-pass computation, no per-row queries.
    """
    name_paths: Dict[str, Set[str]] = {}
    for c in containers:
        name = (c.get('display_name') or '').lower().strip()
        path = (c.get('relative_path') or '').lower().strip()
        if name:
            if name not in name_paths:
                name_paths[name] = set()
            name_paths[name].add(path)
    
    return {name: len(paths) for name, paths in name_paths.items()}


def compute_signals(container: dict, duplicate_map: Dict[str, int]) -> dict:
    """
    Compute deterministic signals for a single resource.
    
    Args:
        container: Resource container dict
        duplicate_map: Pre-computed map from display_name -> distinct path count
    
    Returns:
        {
            'flags': ['duplicate', 'large_folder', ...],
            'suggested_decision': 'HOLD' | None,
            'suggested_reasons': ['outdated', 'duplicate'] | []
        }
    
    Rules:
    - Signals are deterministic and explainable
    - Safe Path is Phase 2 only (always returns None)
    - Staleness alone never suggests HOLD
    """
    flags = []
    suggested_reasons = []
    
    name = (container.get('display_name') or '').lower().strip()
    name_base = name.rsplit('.', 1)[0] if '.' in name else name
    container_type = container.get('container_type', 'file')
    resource_count = container.get('resource_count') or 0
    audience = container.get('audience')
    first_seen = container.get('first_seen')
    scrub_status = container.get('scrub_status')
    
    # 1. Duplicate detection (one-pass via pre-computed map)
    if name and duplicate_map.get(name, 0) > 1:
        flags.append('duplicate')
        suggested_reasons.append('duplicate')
    
    # 2. Large folder
    if container_type == 'folder' and resource_count > 10:
        flags.append('large_folder')
    
    # 3. Risk keywords
    if any(kw in name_base for kw in RISK_KEYWORDS):
        flags.append('risk_keyword')
        if 'outdated' not in suggested_reasons:
            suggested_reasons.append('outdated')
    
    # 4. Compliance keywords
    if any(kw in name_base for kw in COMPLIANCE_KEYWORDS):
        flags.append('compliance_keyword')
        if 'compliance_risk' not in suggested_reasons:
            suggested_reasons.append('compliance_risk')
    
    # 5. Low information (generic name or missing metadata)
    if name_base in GENERIC_NAMES or not audience:
        flags.append('low_information')
        if 'unclear_intent' not in suggested_reasons:
            suggested_reasons.append('unclear_intent')
    
    # 6. Staleness (flag only, never suggests HOLD alone)
    if first_seen and scrub_status == 'not_reviewed':
        try:
            first_seen_dt = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
            if datetime.now(first_seen_dt.tzinfo) - first_seen_dt > timedelta(days=90):
                flags.append('stale')
                # Staleness alone does NOT add to suggested_reasons
        except (ValueError, TypeError):
            pass
    
    # 7. Safe Path - Phase 2 only, always returns None
    # (No implementation in Phase 1)
    
    # Determine suggested decision
    # Only suggest HOLD if we have actual reasons (not just staleness flag)
    suggested_decision = 'HOLD' if suggested_reasons else None
    
    return {
        'flags': flags,
        'suggested_decision': suggested_decision,
        'suggested_reasons': suggested_reasons,
    }


def get_flag_display_text(flags: List[str]) -> str:
    """
    Convert flags to muted display text.
    No badges, no icons, no colors.
    """
    if not flags:
        return ''
    
    labels = {
        'duplicate': 'Possible duplicate',
        'large_folder': 'Large folder',
        'risk_keyword': 'Risk keyword detected',
        'compliance_keyword': 'Compliance keyword',
        'low_information': 'Low information',
        'stale': 'In catalog 90+ days',
    }
    
    return ' · '.join(labels.get(f, f) for f in flags)
