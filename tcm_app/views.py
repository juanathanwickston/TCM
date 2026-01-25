"""
TCM Django Views
================
Django views that call the existing backend functions.
Each view corresponds to a Streamlit page.

FROZEN BACKEND: These views call db.py and services/* functions ONLY.
No new queries, no alternate data paths.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme

# =============================================================================
# AUTH VIEWS
# =============================================================================

def login_view(request):
    """
    Login page - center-aligned card with username/password.
    POST: Authenticate and redirect to dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            # SECURITY: Validate next URL to prevent open redirect attacks
            next_url = request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(
                next_url, 
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'tcm_app/login.html')


@require_http_methods(["POST"])
def logout_view(request):
    """Logout and redirect to login page."""
    logout(request)
    return redirect('login')


# =============================================================================
# PAGE VIEWS (Read-Only for Phase 1)
# =============================================================================

@login_required
def dashboard_view(request):
    """
    Dashboard - Executive metrics overview.
    
    LOCKED SPEC (2026-01-26):
    - All counts use SUM(resource_count) for FILE + LINK only
    - No row counts, no len(), no sum(1 for ...)
    - Status uses normalize_status()
    - Bucket uses normalize_bucket()
    """
    import re
    from collections import defaultdict
    from db import get_active_containers
    from services.scrub_rules import normalize_status
    
    # -------------------------------------------------------------------------
    # LOCAL HELPERS (per locked spec)
    # -------------------------------------------------------------------------
    def normalize_bucket(raw: str) -> str:
        """Normalize bucket field to 'onboarding', 'upskilling', or ''."""
        s = (raw or '').strip().lower()
        # Remove common numeric prefixes like "01_" or "1-"
        s = re.sub(r'^\d+\s*[_-]\s*', '', s)
        if s.startswith('onboarding'):
            return 'onboarding'
        if s.startswith('upskilling'):
            return 'upskilling'
        return ''
    
    def is_resource(c):
        """A resource is a FILE or LINK container."""
        return c.get('container_type') in ('file', 'link')
    
    # -------------------------------------------------------------------------
    # FETCH DATA
    # -------------------------------------------------------------------------
    active = get_active_containers()
    
    # -------------------------------------------------------------------------
    # PRIMARY METRICS (SUM of resource_count)
    # -------------------------------------------------------------------------
    total_resources = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c)
    )
    
    items_remaining = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c) and normalize_status(c.get('scrub_status')) == 'Unreviewed'
    )
    
    # -------------------------------------------------------------------------
    # DECISION BREAKDOWN
    # -------------------------------------------------------------------------
    include_count = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c) and normalize_status(c.get('scrub_status')) == 'Include'
    )
    modify_count = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c) and normalize_status(c.get('scrub_status')) == 'Modify'
    )
    sunset_count = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c) and normalize_status(c.get('scrub_status')) == 'Sunset'
    )
    
    # Decision bar collapse rule
    show_decision_bar = (include_count + modify_count + sunset_count) > 0
    
    # -------------------------------------------------------------------------
    # ONBOARDING VS UPSKILLING
    # -------------------------------------------------------------------------
    onboarding_count = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c) and normalize_bucket(c.get('bucket')) == 'onboarding'
    )
    upskilling_count = sum(
        c.get('resource_count', 0)
        for c in active
        if is_resource(c) and normalize_bucket(c.get('bucket')) == 'upskilling'
    )
    
    # Percentages (avoid divide-by-zero)
    if total_resources > 0:
        onboarding_pct = round(onboarding_count / total_resources * 100, 1)
        upskilling_pct = round(upskilling_count / total_resources * 100, 1)
    else:
        onboarding_pct = 0
        upskilling_pct = 0
    
    # -------------------------------------------------------------------------
    # TRAINING TYPES TABLE (group, sum, sort by count desc then label asc)
    # -------------------------------------------------------------------------
    type_agg = defaultdict(int)
    for c in active:
        if is_resource(c):
            label = (c.get('training_type') or 'Unknown').strip()
            type_agg[label] += c.get('resource_count', 0)
    
    training_types = [
        {
            'type': label,
            'count': count,
            'pct': round(count / total_resources * 100, 1) if total_resources > 0 else 0
        }
        for label, count in type_agg.items()
    ]
    # Sort: count desc, then label asc
    training_types.sort(key=lambda x: (-x['count'], x['type']))
    
    # -------------------------------------------------------------------------
    # TRAINING SOURCES TABLE (group, sum, sort by count desc then label asc)
    # -------------------------------------------------------------------------
    source_agg = defaultdict(int)
    for c in active:
        if is_resource(c):
            label = (c.get('source') or 'Unknown').strip()
            source_agg[label] += c.get('resource_count', 0)
    
    training_sources = [
        {
            'source': label,
            'count': count,
            'pct': round(count / total_resources * 100, 1) if total_resources > 0 else 0
        }
        for label, count in source_agg.items()
    ]
    # Sort: count desc, then label asc
    training_sources.sort(key=lambda x: (-x['count'], x['source']))
    
    # -------------------------------------------------------------------------
    # CONTEXT
    # -------------------------------------------------------------------------
    context = {
        'total_resources': total_resources,
        'items_remaining': items_remaining,
        'include_count': include_count,
        'modify_count': modify_count,
        'sunset_count': sunset_count,
        'show_decision_bar': show_decision_bar,
        'onboarding_count': onboarding_count,
        'upskilling_count': upskilling_count,
        'onboarding_pct': onboarding_pct,
        'upskilling_pct': upskilling_pct,
        'training_types': training_types,
        'training_sources': training_sources,
    }
    
    return render(request, 'tcm_app/dashboard.html', context)


@login_required
def inventory_view(request):
    """
    Inventory - Browse and filter training content.
    GET: Display filtered containers.
    """
    # Import backend functions (frozen - do not modify)
    from db import (
        get_active_departments,
        get_active_training_types,
        get_active_containers_filtered,
    )
    from services.container_service import compute_file_count, TRAINING_TYPE_LABELS
    from services.sales_stage import SALES_STAGES, SALES_STAGE_LABELS
    from services.scrub_rules import CANONICAL_AUDIENCES
    
    # Get filter values from GET params
    department = request.GET.get('department', '')
    training_type = request.GET.get('training_type', '')
    sales_stage = request.GET.get('sales_stage', '')
    audience = request.GET.get('audience', '')
    
    # Fetch filter options
    departments = get_active_departments()
    training_types = get_active_training_types(department if department else None)
    
    # Fetch filtered containers
    containers = get_active_containers_filtered(
        primary_department=department if department else None,
        training_type=training_type if training_type else None,
        sales_stage=sales_stage if sales_stage else None,
    )
    
    # Apply audience filter client-side (matches Streamlit behavior)
    if audience == 'unassigned':
        containers = [c for c in containers if not c.get('audience')]
    elif audience and audience != 'all':
        containers = [c for c in containers if c.get('audience') == audience]
    
    # Compute totals - SUM(resource_count) over filtered containers
    total_resources = sum(c.get('resource_count', 0) for c in containers)
    items_inside_folders = sum(compute_file_count(c) for c in containers)
    
    context = {
        'containers': containers,
        'departments': departments,
        'training_types': training_types,
        'training_type_labels': TRAINING_TYPE_LABELS,
        'sales_stages': SALES_STAGES,
        'sales_stage_labels': SALES_STAGE_LABELS,
        'audiences': CANONICAL_AUDIENCES,
        'total_resources': total_resources,
        'items_inside_folders': items_inside_folders,
        # Current filter values (for preserving state after edit)
        'current_department': department,
        'current_training_type': training_type,
        'current_sales_stage': sales_stage,
        'current_audience': audience,
    }
    
    return render(request, 'tcm_app/inventory.html', context)


def _redirect_with_filters(request, view_name='inventory'):
    """
    Helper to redirect while preserving filter state from POST params.
    Reusable for any POST action that needs to return to a filtered view.
    """
    from urllib.parse import urlencode
    
    params = {}
    if request.POST.get('department'):
        params['department'] = request.POST.get('department')
    if request.POST.get('training_type'):
        params['training_type'] = request.POST.get('training_type')
    if request.POST.get('sales_stage'):
        params['sales_stage'] = request.POST.get('sales_stage')
    if request.POST.get('audience_filter'):
        params['audience'] = request.POST.get('audience_filter')
    
    if params:
        return redirect(f'/{view_name}/?{urlencode(params)}')
    return redirect(view_name)


@login_required
@require_http_methods(["POST"])
def update_audience_view(request):
    """
    Update audience for a single container.
    CSRF-protected POST endpoint.
    Calls frozen backend: update_audience_bulk([container_key], audience)
    """
    from db import update_audience_bulk
    from services.scrub_rules import CANONICAL_AUDIENCES
    
    container_key = request.POST.get('container_key', '').strip()
    new_audience = request.POST.get('audience', '').strip()
    
    # Validate inputs - preserve filter state on error redirects
    if not container_key:
        messages.error(request, 'Invalid container key')
        return _redirect_with_filters(request)
    
    if not new_audience:
        messages.error(request, 'Audience cannot be empty')
        return _redirect_with_filters(request)
    
    if new_audience not in CANONICAL_AUDIENCES:
        messages.error(request, f'Invalid audience value: {new_audience}')
        return _redirect_with_filters(request)
    
    # Call frozen backend function - exactly one container
    update_audience_bulk([container_key], new_audience)
    
    messages.success(request, f'Audience updated to "{new_audience}"')
    
    return _redirect_with_filters(request)


@login_required
def scrubbing_view(request):
    """
    Scrubbing - Queue-based triage workflow.
    
    PARITY CONTRACT:
    - Read: get_active_containers() only
    - Filter: QUEUE_FILTERS = ["Unreviewed", "Include", "Modify", "Sunset", "All"]
    - Sort: resource_count DESC, relative_path ASC
    - No new validation gates (Streamlit didn't gate on owner/audience/notes)
    """
    # Import backend functions (frozen - do not modify)
    from db import get_active_containers
    from services.scrub_rules import normalize_status, CANONICAL_SCRUB_STATUSES, CANONICAL_AUDIENCES
    from services.sales_stage import SALES_STAGES
    
    # Queue filter options (exact Streamlit parity)
    QUEUE_FILTERS = ["Unreviewed", "Include", "Modify", "Sunset", "All"]
    
    # Get filter from GET params
    queue_filter = request.GET.get('queue_filter', 'Unreviewed')
    if queue_filter not in QUEUE_FILTERS:
        queue_filter = 'Unreviewed'
    
    # Fetch all active containers (same as Streamlit)
    containers = get_active_containers()
    
    # Compute queue counts using normalize_status
    queue_counts = {'Unreviewed': 0, 'Include': 0, 'Modify': 0, 'Sunset': 0, 'total': len(containers)}
    for c in containers:
        normalized = normalize_status(c.get('scrub_status'))
        if normalized in queue_counts:
            queue_counts[normalized] += 1
    
    # Filter containers using normalize_status (exact Streamlit logic)
    if queue_filter == "All":
        filtered = containers
    else:
        filtered = [c for c in containers if normalize_status(c.get('scrub_status')) == queue_filter]
    
    # Sort: resource_count DESC, then relative_path ASC (exact Streamlit sort)
    filtered = sorted(filtered, key=lambda c: (-(c.get('resource_count') or 0), c.get('relative_path', '')))
    
    # Add normalized status to each container for display
    for c in filtered:
        c['normalized_status'] = normalize_status(c.get('scrub_status'))
    
    context = {
        'containers': filtered,
        'queue_filters': QUEUE_FILTERS,
        'queue_counts': queue_counts,
        'current_queue_filter': queue_filter,
        'scrub_statuses': CANONICAL_SCRUB_STATUSES,
        'audiences': CANONICAL_AUDIENCES,
        'sales_stages': SALES_STAGES,
        'total_count': queue_counts['total'],
        'reviewed_count': queue_counts['total'] - queue_counts['Unreviewed'],
    }
    
    return render(request, 'tcm_app/scrubbing.html', context)


@login_required
@require_http_methods(["POST"])
def save_scrub_view(request):
    """
    Save scrub decision for a single container.
    
    PARITY CONTRACT:
    - Calls update_container_scrub with owner='' ALWAYS (Streamlit behavior)
    - Maps "Unreviewed" → 'not_reviewed' for storage
    - Does NOT gate on missing audience/notes/owner (Streamlit didn't)
    - Calls update_sales_stage if sales_stage provided
    """
    from db import update_container_scrub, update_sales_stage
    from services.scrub_rules import VALID_SCRUB_DECISIONS, CANONICAL_AUDIENCES
    from services.sales_stage import SALES_STAGE_KEYS
    from urllib.parse import urlencode
    
    container_key = request.POST.get('container_key', '').strip()
    decision_input = request.POST.get('decision', '').strip()
    notes = request.POST.get('notes', '').strip() or None
    audience = request.POST.get('audience', '').strip() or None
    sales_stage = request.POST.get('sales_stage', '').strip() or None
    queue_filter = request.POST.get('queue_filter', 'Unreviewed')
    
    # Validate container_key
    if not container_key:
        messages.error(request, 'Invalid container key')
        return redirect(f'/scrubbing/?queue_filter={queue_filter}')
    
    # Map "Unreviewed" → 'not_reviewed' for storage
    if decision_input == 'Unreviewed':
        decision = 'not_reviewed'
    else:
        decision = decision_input  # Include, Modify, Sunset as-is
    
    # Validate decision
    if decision not in VALID_SCRUB_DECISIONS:
        messages.error(request, f'Invalid decision: {decision_input}')
        return redirect(f'/scrubbing/?queue_filter={queue_filter}')
    
    # Validate audience if provided (optional - no gate)
    if audience and audience not in CANONICAL_AUDIENCES:
        messages.error(request, f'Invalid audience: {audience}')
        return redirect(f'/scrubbing/?queue_filter={queue_filter}')
    
    # Validate sales_stage if provided - sanitize invalid to None with warning
    if sales_stage and sales_stage not in SALES_STAGE_KEYS:
        messages.warning(request, f'Invalid sales stage "{sales_stage}" ignored')
        sales_stage = None
    
    # Call frozen backend: update_container_scrub with owner='' (Streamlit parity)
    update_container_scrub(
        container_key=container_key,
        decision=decision,
        owner='',  # ALWAYS empty string (Streamlit behavior)
        notes=notes,
        reasons=None,  # Not used in current workflow
        resource_count_override=None,
        audience=audience,
    )
    
    # Call frozen backend: update_sales_stage (None clears it)
    update_sales_stage(
        container_key=container_key,
        stage=sales_stage,
    )
    
    messages.success(request, 'Saved')
    
    # Redirect back to queue with filter preserved
    return redirect(f'/scrubbing/?queue_filter={queue_filter}')


@login_required
def investment_view(request):
    """
    Investment - Build/Buy/Assign decisions.
    
    PARITY CONTRACT:
    - Investment queue = containers where normalize_status(scrub_status) == 'Modify'
    - This includes raw values: 'Modify', 'modify', 'gap' (all normalize to 'Modify')
    - Uses get_active_containers() with the canonical is_archived=0, is_placeholder=0 predicate
    - No new validation gates
    """
    from db import get_active_containers
    from services.scrub_rules import normalize_status
    from models.enums import InvestDecision
    
    # CANONICAL READ: get_active_containers (same predicate as everywhere else)
    all_containers = get_active_containers()
    
    # Investment queue = containers whose normalize_status == 'Modify'
    # This includes raw 'Modify', 'modify', and legacy 'gap'
    containers = [
        c for c in all_containers 
        if normalize_status(c.get('scrub_status')) == 'Modify'
    ]
    
    # Sort: resource_count desc, relative_path asc (parity with legacy)
    containers.sort(key=lambda c: (-c.get('resource_count', 1), c.get('relative_path', '')))
    
    # Read filter params
    filter_decision = request.GET.get('decision_filter', 'All')
    
    # Apply decision filter only (no scrub filter needed - all are Modify)
    filtered = containers
    if filter_decision != 'All':
        if filter_decision == 'Pending':
            filtered = [c for c in filtered if not c.get('invest_decision')]
        else:
            filtered = [c for c in filtered if c.get('invest_decision') == filter_decision]
    
    # Queue counts
    decided_count = len([c for c in containers if c.get('invest_decision')])
    pending_count = len(containers) - decided_count
    
    # InvestDecision choices - exact parity with legacy enum
    invest_choices = InvestDecision.choices()  # ['build', 'buy', 'assign_sme', 'defer']
    invest_labels = InvestDecision.display_labels()  # {'build': 'Build', 'buy': 'Buy', ...}
    
    context = {
        'containers': filtered,
        'total_count': len(containers),
        'decided_count': decided_count,
        'pending_count': pending_count,
        # invest_choices as list of (value, label) tuples for template iteration
        'invest_choices': [(c, invest_labels.get(c, c.title())) for c in invest_choices],
        'filter_decision': filter_decision,
        # Decision dropdown options: All, Pending (filter concept, not stored), then enum values
        'decision_options': [('All', 'All'), ('Pending', 'Pending')] + [(c, invest_labels.get(c, c)) for c in invest_choices],
    }
    
    return render(request, 'tcm_app/investment.html', context)


@login_required
@require_http_methods(["POST"])
def save_investment_view(request):
    """
    Save investment decision for a single container.
    
    PARITY CONTRACT:
    - Calls update_container_invest with (container_key, decision, owner, effort, notes)
    - Does NOT enforce extra validation gates beyond what legacy did
    - Preserves filter state on redirect
    """
    from db import update_container_invest
    from models.enums import InvestDecision
    
    container_key = request.POST.get('container_key', '').strip()
    decision = request.POST.get('decision', '').strip() or None
    owner = request.POST.get('owner', '').strip() or ''
    effort = request.POST.get('effort', '').strip() or None
    notes = request.POST.get('notes', '').strip() or None
    
    # Preserve filters for redirect
    decision_filter = request.POST.get('decision_filter', 'All')
    
    # Validate container_key
    if not container_key:
        messages.error(request, 'Invalid container key')
        return redirect(f'/investment/?decision_filter={decision_filter}')
    
    # Validate decision if provided
    valid_decisions = InvestDecision.choices()
    if decision and decision not in valid_decisions:
        messages.warning(request, f'Invalid decision "{decision}" ignored')
        decision = None
    
    # Call frozen backend: update_container_invest
    update_container_invest(
        container_key=container_key,
        decision=decision,
        owner=owner,
        effort=effort,
        notes=notes,
    )
    
    messages.success(request, 'Saved')
    
    # Redirect back with filters preserved
    return redirect(f'/investment/?decision_filter={decision_filter}')


# =============================================================================
# TOOLS VIEWS (Phase 5)
# =============================================================================

@login_required
def tools_view(request):
    """
    Tools - Import, sync, and admin utilities.
    
    GET always returns 200 (no service calls).
    Any authenticated user can view.
    All POST actions require superuser.
    """
    import os
    
    # SharePoint configuration check (for UI display only - never 500)
    sharepoint_enabled = os.environ.get('SHAREPOINT_SYNC_ENABLED', '').lower() == 'true'
    sharepoint_tenant = os.environ.get('SHAREPOINT_TENANT_ID', '')
    sharepoint_client = os.environ.get('SHAREPOINT_CLIENT_ID', '')
    sharepoint_configured = sharepoint_enabled and sharepoint_tenant and sharepoint_client
    
    context = {
        'is_superuser': request.user.is_superuser,
        'sharepoint_configured': sharepoint_configured,
    }
    
    return render(request, 'tcm_app/tools.html', context)


@login_required
@require_http_methods(["POST"])
def import_zip_view(request):
    """
    Import containers from ZIP file.
    
    SUPERUSER ONLY.
    250MB size limit enforced server-side.
    PRG pattern with Django messages.
    NEVER 500s - all errors handled with message + redirect.
    """
    # Superuser gate
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied. Superuser required.")
    
    try:
        from services.container_service import import_from_zip
        from pathlib import Path
        import tempfile
        
        # Check file present (use .get() to avoid KeyError)
        uploaded = request.FILES.get('zipfile')
        if not uploaded:
            messages.error(request, 'No file uploaded')
            return redirect('tools')
        
        # Validate extension first (cheap check)
        if not uploaded.name.lower().endswith('.zip'):
            messages.error(request, 'Only .zip files are allowed')
            return redirect('tools')
        
        # 250MB limit (250 * 1024 * 1024 = 262144000 bytes)
        max_size = 250 * 1024 * 1024
        if uploaded.size > max_size:
            messages.error(request, f'File too large ({uploaded.size // (1024*1024)}MB). Maximum is 250MB.')
            return redirect('tools')
        
        # Save to temp file with unique name (no path traversal possible)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                for chunk in uploaded.chunks():
                    tmp.write(chunk)
                temp_path = tmp.name
            
            # Import via frozen backend
            result = import_from_zip(temp_path)
            
            # Success message with stats
            messages.success(
                request,
                f"Import complete: {result.get('new_containers', 0)} new, "
                f"{result.get('updated_containers', 0)} updated, "
                f"{result.get('skipped', 0)} skipped"
            )
            
            # Show errors if any
            for err in result.get('errors', [])[:3]:
                messages.warning(request, err)
                
        finally:
            # Always clean up temp file
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
                
    except Exception as e:
        messages.error(request, f'Import failed: {str(e)}')
    
    return redirect('tools')


@login_required
@require_http_methods(["POST"])
def sync_sharepoint_view(request):
    """
    Sync containers from SharePoint.
    
    SUPERUSER ONLY.
    ENV-GATED: Only runs if SHAREPOINT_SYNC_ENABLED=true and creds exist.
    Fail-closed with message if not configured.
    """
    import os
    
    # Superuser gate
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied. Superuser required.")
    
    # Re-check env gating server-side (fail-closed)
    sharepoint_enabled = os.environ.get('SHAREPOINT_SYNC_ENABLED', '').lower() == 'true'
    sharepoint_tenant = os.environ.get('SHAREPOINT_TENANT_ID', '')
    sharepoint_client = os.environ.get('SHAREPOINT_CLIENT_ID', '')
    
    if not (sharepoint_enabled and sharepoint_tenant and sharepoint_client):
        messages.error(request, 'SharePoint sync not configured. Set SHAREPOINT_SYNC_ENABLED=true and required credentials.')
        return redirect('tools')
    
    try:
        from services.sharepoint_service import sync_from_sharepoint, is_sharepoint_enabled
        
        # Second guard: service-level check
        if not is_sharepoint_enabled():
            messages.error(request, 'SharePoint sync is disabled at service level.')
            return redirect('tools')
        
        result = sync_from_sharepoint()
        
        messages.success(
            request,
            f"SharePoint sync complete: {result.get('added', 0)} added, "
            f"{result.get('archived', 0)} archived, "
            f"{result.get('total', 0)} active"
        )
        
        if result.get('scope_violations', 0) > 0:
            messages.warning(request, f"{result['scope_violations']} scope violations detected (see logs)")
            
    except Exception as e:
        messages.error(request, f'SharePoint sync failed: {str(e)}')
    
    return redirect('tools')


@login_required
@require_http_methods(["POST"])
def clear_all_data_view(request):
    """
    Clear all container data (HARD DELETE).
    
    SUPERUSER ONLY.
    Requires exact typed confirmation: "CLEAR ALL DATA".
    This action cannot be undone.
    """
    # Superuser gate
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied. Superuser required.")
    
    from db import clear_containers
    
    confirmation = request.POST.get('confirmation', '').strip()
    
    # Server-side confirmation check (exact match required)
    if confirmation != 'CLEAR ALL DATA':
        messages.error(request, 'Confirmation text did not match. No data was deleted.')
        return redirect('tools')
    
    try:
        clear_containers()
        messages.success(request, 'All container data has been permanently deleted.')
    except Exception as e:
        messages.error(request, f'Clear failed: {str(e)}')
    
    return redirect('tools')

