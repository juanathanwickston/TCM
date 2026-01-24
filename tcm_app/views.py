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
    Calls: kpi_service functions.
    """
    # Import backend functions (frozen - do not modify)
    from services.kpi_service import (
        get_submission_summary,
        get_scrub_status_breakdown,
        get_source_breakdown,
        get_training_type_breakdown,
        get_duplicate_count,
    )
    from db import get_active_containers, get_sales_stage_breakdown
    from services.container_service import compute_file_count
    
    # Fetch data via existing backend
    summary = get_submission_summary()
    status = get_scrub_status_breakdown()
    sources = get_source_breakdown()
    types = get_training_type_breakdown()
    dupes = get_duplicate_count()
    stages = get_sales_stage_breakdown()
    
    # Compute total content items
    active_containers = get_active_containers()
    total_content_items = sum(compute_file_count(c) for c in active_containers)
    
    context = {
        'summary': summary,
        'status': status,
        'sources': sources[:10] if sources else [],
        'types': types[:10] if types else [],
        'duplicates': dupes,
        'stages': stages,
        'total_content_items': total_content_items,
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
    
    # Validate inputs
    if not container_key:
        messages.error(request, 'Invalid container key')
        return redirect('inventory')
    
    if not new_audience:
        messages.error(request, 'Audience cannot be empty')
        return redirect('inventory')
    
    if new_audience not in CANONICAL_AUDIENCES:
        messages.error(request, f'Invalid audience value: {new_audience}')
        return redirect('inventory')
    
    # Call frozen backend function - exactly one container
    update_audience_bulk([container_key], new_audience)
    
    messages.success(request, f'Audience updated to "{new_audience}"')
    
    # Preserve filter state in redirect
    redirect_url = '/inventory/?'
    params = []
    if request.POST.get('department'):
        params.append(f"department={request.POST.get('department')}")
    if request.POST.get('training_type'):
        params.append(f"training_type={request.POST.get('training_type')}")
    if request.POST.get('sales_stage'):
        params.append(f"sales_stage={request.POST.get('sales_stage')}")
    if request.POST.get('audience_filter'):
        params.append(f"audience={request.POST.get('audience_filter')}")
    
    return redirect(redirect_url + '&'.join(params) if params else 'inventory')


@login_required
def scrubbing_view(request):
    """
    Scrubbing - Queue-based triage workflow.
    Phase 1: Placeholder, full implementation in Phase 4.
    """
    return render(request, 'tcm_app/scrubbing.html', {
        'phase': 'Phase 1 - Coming in Phase 4',
    })


@login_required
def investment_view(request):
    """
    Investment - Build/Buy/Assign decisions.
    Phase 1: Placeholder, full implementation in Phase 4.
    """
    return render(request, 'tcm_app/investment.html', {
        'phase': 'Phase 1 - Coming in Phase 4',
    })


@login_required
def tools_view(request):
    """
    Tools - Import, export, admin utilities.
    SUPERUSER ONLY (John).
    """
    # HARD 403 GATE
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied. Superuser required.")
    
    return render(request, 'tcm_app/tools.html', {
        'phase': 'Phase 1 - Coming in Phase 5',
    })
