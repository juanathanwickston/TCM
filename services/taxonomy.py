"""
TCM Taxonomy Constants
======================
Single source of truth for ALL taxonomy values in the Training Catalogue Manager.

This module consolidates all canonical values, validation functions, and
relationship rules. Import from here instead of hardcoding values.

Usage:
    from services.taxonomy import (
        CANONICAL_BUCKETS, CANONICAL_AUDIENCES, validate_taxonomy_update
    )
"""

from typing import Dict, List, Optional, Tuple

# =============================================================================
# RE-EXPORT EXISTING CONSTANTS (maintain compatibility)
# =============================================================================

from services.scrub_rules import (
    CANONICAL_AUDIENCES,
    CANONICAL_SCRUB_STATUSES,
    VALID_SCRUB_DECISIONS,
    VALID_SCRUB_REASONS,
    REASON_LABELS,
)

from services.sales_stage import (
    SALES_STAGES,
    SALES_STAGE_KEYS,
    SALES_STAGE_LABELS,
)


# =============================================================================
# 1. BUCKETS - What stage of employment
# =============================================================================

CANONICAL_BUCKETS = ('Onboarding', 'Upskilling')

BUCKET_DEFINITIONS = {
    'Onboarding': 'Foundational, role-critical knowledge for new hires. Assumes no prior knowledge.',
    'Upskilling': 'Performance improvement for existing team members. Assumes prior experience.',
}


# =============================================================================
# 2. INVESTMENT DECISION - How to address Modify items
# =============================================================================

VALID_INVEST_DECISIONS = ('build', 'buy', 'assign_sme', 'defer')

INVEST_DECISION_LABELS = {
    'build': 'Build (Create Internally)',
    'buy': 'Buy (Purchase from Vendor)',
    'assign_sme': 'Assign SME (Delegate to Expert)',
    'defer': 'Defer (Postpone Decision)',
}

INVEST_DECISION_DEFINITIONS = {
    'build': 'Create content using internal resources and expertise.',
    'buy': 'Purchase ready-made content from an external vendor.',
    'assign_sme': 'Assign a subject matter expert to develop or review.',
    'defer': 'Postpone the decision for later evaluation.',
}


# =============================================================================
# 3. INVESTMENT EFFORT - Time estimate
# =============================================================================

VALID_INVEST_EFFORT = ('<1w', '1-2w', '2-4w', '1-2m', '2-3m', '3m+')

INVEST_EFFORT_LABELS = {
    '<1w': 'Less than 1 week',
    '1-2w': '1-2 weeks',
    '2-4w': '2-4 weeks',
    '1-2m': '1-2 months',
    '2-3m': '2-3 months',
    '3m+': '3+ months',
}


# =============================================================================
# 4. INVESTMENT COST - Budget estimate
# =============================================================================

VALID_INVEST_COST = ('$0', '<$500', '$500-2k', '$2k-5k', '$5k-10k', '$10k+')

INVEST_COST_LABELS = {
    '$0': '$0 (Internal)',
    '<$500': 'Under $500',
    '$500-2k': '$500 - $2,000',
    '$2k-5k': '$2,000 - $5,000',
    '$5k-10k': '$5,000 - $10,000',
    '$10k+': '$10,000+',
}


# =============================================================================
# 5. TRAINING TYPES - Content format (from container_service.py)
# =============================================================================

# Import from authoritative source - container_service.py
from services.container_service import TRAINING_TYPE_LABELS

# Valid training type keys (used in database)
VALID_TRAINING_TYPES = tuple(TRAINING_TYPE_LABELS.keys())
# = ('instructor_led_in_person', 'instructor_led_virtual', 'self_directed',
#    'video_on_demand', 'job_aids', 'resources')

TRAINING_TYPE_DEFINITIONS = {
    'instructor_led_in_person': 'Live training session with an in-person instructor.',
    'instructor_led_virtual': 'Live training session with a virtual/remote instructor.',
    'self_directed': 'Self-paced learning content the user completes independently.',
    'video_on_demand': 'Pre-recorded video content available on demand.',
    'job_aids': 'Quick reference documents, checklists, or guides.',
    'resources': 'General resources, documents, or reference materials.',
}


# =============================================================================
# 6. DEPARTMENTS - Dynamic from folder structure (L0 level)
# =============================================================================

# Departments are NOT hardcoded - they come from SharePoint folder structure.
# Use get_valid_departments() to query actual values from database.

def get_valid_departments() -> List[str]:
    """
    Get valid departments from database (canonical source).
    
    Departments are derived from the L0 folder structure in SharePoint,
    not a hardcoded list. This ensures validation matches actual data.
    
    Returns:
        List of department names currently in the catalog
    """
    import db
    results = db.execute(
        "SELECT DISTINCT primary_department FROM resources "
        "WHERE primary_department IS NOT NULL AND primary_department != '' "
        "AND is_archived = 0 "
        "ORDER BY primary_department",
        fetch="all"
    )
    return [r['primary_department'] for r in results]


# Legacy constant for backwards compatibility (DO NOT USE FOR VALIDATION)
# Use get_valid_departments() instead
_LEGACY_DEPARTMENTS = (
    'Direct', 'Indirect', 'Integration', 'FI',
    'Partner Management', 'Operations', 'Compliance',
)


# =============================================================================
# TAXONOMY RELATIONSHIPS
# =============================================================================

# Scrub status workflow transitions
SCRUB_STATUS_WORKFLOW = {
    'not_reviewed': 'Needs scrubbing review',
    'Include': 'Complete - ready to use',
    'Modify': 'Triggers Investment queue',
    'Sunset': 'Scheduled for removal/archival',
}

# Fields required when setting specific scrub statuses
SCRUB_STATUS_REQUIRED_FIELDS = {
    'Modify': ['scrub_reason'],  # Must have at least one reason
    'Sunset': [],  # No additional requirements
    'Include': [],  # No additional requirements
}

# Fields triggered by Modify status
INVESTMENT_FIELDS = ['invest_decision', 'invest_effort', 'invest_cost', 'invest_notes']


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_taxonomy_update(updates: Dict) -> Tuple[bool, str]:
    """
    Validate that a taxonomy update respects all rules.
    
    Returns:
        (is_valid, error_message) - error_message is empty if valid
    """
    errors = []
    
    # Rule 1: Validate bucket
    if updates.get('bucket'):
        if updates['bucket'] not in CANONICAL_BUCKETS:
            errors.append(f"Invalid bucket '{updates['bucket']}'. Use: {', '.join(CANONICAL_BUCKETS)}")
    
    # Rule 2: Validate audience
    if updates.get('audience'):
        if updates['audience'] not in CANONICAL_AUDIENCES:
            errors.append(f"Invalid audience '{updates['audience']}'. Use: {', '.join(CANONICAL_AUDIENCES)}")
    
    # Rule 3: Validate scrub_status
    if updates.get('scrub_status'):
        if updates['scrub_status'] not in VALID_SCRUB_DECISIONS:
            errors.append(f"Invalid scrub_status '{updates['scrub_status']}'. Use: {', '.join(VALID_SCRUB_DECISIONS)}")
    
    # Rule 4: Modify requires scrub_reason
    if updates.get('scrub_status') == 'Modify':
        if not updates.get('scrub_reason') and not updates.get('scrub_reasons'):
            errors.append("Modify status requires a scrub_reason. Options: " + 
                         ", ".join(REASON_LABELS.values()))
    
    # Rule 5: Validate scrub_reason if provided
    if updates.get('scrub_reason'):
        if updates['scrub_reason'] not in VALID_SCRUB_REASONS:
            errors.append(f"Invalid scrub_reason '{updates['scrub_reason']}'. Use: {', '.join(VALID_SCRUB_REASONS)}")
    
    # Rule 6: Validate sales_stage
    if updates.get('sales_stage'):
        if updates['sales_stage'] not in SALES_STAGE_KEYS:
            errors.append(f"Invalid sales_stage '{updates['sales_stage']}'. Use: {', '.join(SALES_STAGE_KEYS)}")
    
    # Rule 7: Validate invest_decision
    if updates.get('invest_decision'):
        if updates['invest_decision'] not in VALID_INVEST_DECISIONS:
            errors.append(f"Invalid invest_decision '{updates['invest_decision']}'. Use: {', '.join(VALID_INVEST_DECISIONS)}")
    
    # Rule 8: Validate invest_effort
    if updates.get('invest_effort'):
        if updates['invest_effort'] not in VALID_INVEST_EFFORT:
            errors.append(f"Invalid invest_effort '{updates['invest_effort']}'. Use: {', '.join(VALID_INVEST_EFFORT)}")
    
    # Rule 9: Validate invest_cost
    if updates.get('invest_cost'):
        if updates['invest_cost'] not in VALID_INVEST_COST:
            errors.append(f"Invalid invest_cost '{updates['invest_cost']}'. Use: {', '.join(VALID_INVEST_COST)}")
    
    # Rule 10: Validate training_type
    if updates.get('training_type'):
        if updates['training_type'] not in VALID_TRAINING_TYPES:
            errors.append(f"Invalid training_type '{updates['training_type']}'. Use: {', '.join(VALID_TRAINING_TYPES)}")
    
    # Rule 11: Validate primary_department (dynamic from database)
    if updates.get('primary_department'):
        valid_depts = get_valid_departments()
        if valid_depts and updates['primary_department'] not in valid_depts:
            errors.append(f"Invalid primary_department '{updates['primary_department']}'. Valid: {', '.join(valid_depts)}")
    
    if errors:
        return False, errors[0]  # Return first error
    
    return True, ""


def get_field_options(field_name: str) -> List[str]:
    """
    Get valid options for a taxonomy field.
    
    Args:
        field_name: Name of the field (e.g., 'bucket', 'audience')
    
    Returns:
        List of valid values for the field
    """
    field_map = {
        'bucket': list(CANONICAL_BUCKETS),
        'audience': list(CANONICAL_AUDIENCES),
        'scrub_status': list(CANONICAL_SCRUB_STATUSES),
        'scrub_reason': list(VALID_SCRUB_REASONS),
        'sales_stage': list(SALES_STAGE_KEYS),
        'invest_decision': list(VALID_INVEST_DECISIONS),
        'invest_effort': list(VALID_INVEST_EFFORT),
        'invest_cost': list(VALID_INVEST_COST),
        'training_type': list(VALID_TRAINING_TYPES),
        'primary_department': get_valid_departments(),
    }
    return field_map.get(field_name, [])


def get_field_labels(field_name: str) -> Dict[str, str]:
    """
    Get key→label mapping for a taxonomy field.
    
    Args:
        field_name: Name of the field
    
    Returns:
        Dictionary mapping keys to display labels
    """
    label_map = {
        'bucket': {k: k for k in CANONICAL_BUCKETS},
        'audience': {k: k for k in CANONICAL_AUDIENCES},
        'scrub_status': {k: k for k in CANONICAL_SCRUB_STATUSES},
        'scrub_reason': REASON_LABELS,
        'sales_stage': SALES_STAGE_LABELS,
        'invest_decision': INVEST_DECISION_LABELS,
        'invest_effort': INVEST_EFFORT_LABELS,
        'invest_cost': INVEST_COST_LABELS,
        'training_type': {k: k for k in VALID_TRAINING_TYPES},
        'primary_department': {k: k for k in CANONICAL_DEPARTMENTS},
    }
    return label_map.get(field_name, {})


def get_field_definition(field_name: str) -> str:
    """
    Get the definition/purpose of a taxonomy field.
    
    Args:
        field_name: Name of the field
    
    Returns:
        Human-readable definition of the field
    """
    definitions = {
        'bucket': 'Which stage of employment the training supports (Onboarding for new hires, Upskilling for existing employees).',
        'audience': 'The primary target learner role who will consume this training content.',
        'scrub_status': 'The review decision that drives workflow: Include (done), Modify (to Investment), Sunset (removal).',
        'scrub_reason': 'Why content is marked Modify or Sunset. Required for Modify status.',
        'sales_stage': 'Where in the sales cycle this training applies. Only relevant for sales-related audiences.',
        'invest_decision': 'How to address content marked Modify: Build, Buy, Assign SME, or Defer.',
        'invest_effort': 'Estimated time to complete the investment work.',
        'invest_cost': 'Estimated budget required for the investment.',
        'training_type': 'The format/delivery method of the training content.',
        'primary_department': 'Which department owns and maintains this content.',
    }
    return definitions.get(field_name, f"Unknown field: {field_name}")


def get_field_rule(field_name: str) -> str:
    """
    Get the decision rule for choosing a value in this field.
    
    Args:
        field_name: Name of the field
    
    Returns:
        Rule of thumb for making decisions about this field
    """
    rules = {
        'bucket': 'If content assumes prior knowledge → Upskilling. If foundational for new hires → Onboarding.',
        'audience': 'Select based on WHO is the primary target learner, not who might also benefit.',
        'scrub_status': 'Include = ready to use. Modify = needs work (triggers Investment). Sunset = remove from catalog.',
        'scrub_reason': 'Choose the primary reason. For multiple issues, select the most impactful one.',
        'sales_stage': 'Match to the sales cycle phase. Leave empty if not sales-related.',
        'invest_decision': 'Build if you have expertise. Buy if faster/cheaper externally. Assign SME if complex domain. Defer if uncertain.',
        'invest_effort': 'Estimate realistically. Include review cycles in the estimate.',
        'invest_cost': 'Include all costs: vendor fees, contractor time, tools. $0 = fully internal.',
        'training_type': 'Classify by primary format. If mixed, choose the dominant delivery method.',
        'primary_department': 'Assign to the department with subject matter ownership, not just who requested.',
    }
    return rules.get(field_name, "No specific rule defined.")


# =============================================================================
# TAXONOMY FIELD METADATA (for chatbot explain_taxonomy function)
# =============================================================================

def get_taxonomy_fields() -> Dict[str, dict]:
    """
    Get taxonomy field metadata for the explain_taxonomy function.
    
    This is a function instead of a constant to enable lazy loading
    of dynamic values (like departments from database).
    
    Returns:
        Dictionary of field metadata with name, definition, values, and rule
    """
    return {
        'bucket': {
            'name': 'Bucket',
            'definition': get_field_definition('bucket'),
            'values': get_field_options('bucket'),
            'rule': get_field_rule('bucket'),
        },
        'audience': {
            'name': 'Audience',
            'definition': get_field_definition('audience'),
            'values': get_field_options('audience'),
            'rule': get_field_rule('audience'),
        },
        'scrub_status': {
            'name': 'Scrub Status',
            'definition': get_field_definition('scrub_status'),
            'values': get_field_options('scrub_status'),
            'rule': get_field_rule('scrub_status'),
        },
        'scrub_reason': {
            'name': 'Scrub Reason',
            'definition': get_field_definition('scrub_reason'),
            'values': get_field_options('scrub_reason'),
            'rule': get_field_rule('scrub_reason'),
        },
        'sales_stage': {
            'name': 'Sales Stage',
            'definition': get_field_definition('sales_stage'),
            'values': get_field_options('sales_stage'),
            'rule': get_field_rule('sales_stage'),
        },
        'invest_decision': {
            'name': 'Investment Decision',
            'definition': get_field_definition('invest_decision'),
            'values': get_field_options('invest_decision'),
            'rule': get_field_rule('invest_decision'),
        },
        'invest_effort': {
            'name': 'Investment Effort',
            'definition': get_field_definition('invest_effort'),
            'values': get_field_options('invest_effort'),
            'rule': get_field_rule('invest_effort'),
        },
        'invest_cost': {
            'name': 'Investment Cost',
            'definition': get_field_definition('invest_cost'),
            'values': get_field_options('invest_cost'),
            'rule': get_field_rule('invest_cost'),
        },
        'training_type': {
            'name': 'Training Type',
            'definition': get_field_definition('training_type'),
            'values': get_field_options('training_type'),
            'rule': get_field_rule('training_type'),
        },
        'primary_department': {
            'name': 'Primary Department',
            'definition': get_field_definition('primary_department'),
            'values': get_field_options('primary_department'),
            'rule': get_field_rule('primary_department'),
        },
    }


# Legacy alias for backwards compatibility
# DEPRECATED: Use get_taxonomy_fields() instead
TAXONOMY_FIELDS = None  # Set to None to force usage of function

