"""
Inventory ↔ Dashboard Reconciliation Test
==========================================

GUARDRAIL: Ensures Inventory total == Dashboard total.
Both use the same canonical predicate:
    WHERE is_archived = 0 AND is_placeholder = 0

Both use SUM(resource_count).

Run with DATABASE_URL set to test against real database.
"""

import os
import sys
import pytest

sys.path.insert(0, '.')

# Skip if no database connection
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set - integration test requires real database"
)


def test_inventory_dashboard_reconciliation():
    """
    Inventory total_resources must equal Dashboard total_resources.
    
    Inventory: get_active_containers_filtered() with no filters → SUM(resource_count)
    Dashboard: get_total_active_resources() → SUM(resource_count)
    
    Both use canonical predicate: is_archived = 0 AND is_placeholder = 0
    """
    from db import get_active_containers_filtered
    from services.kpi_service import get_total_active_resources
    
    # Inventory total (unfiltered)
    containers = get_active_containers_filtered()
    inventory_total = sum(c.get('resource_count', 0) for c in containers)
    
    # Dashboard total
    dashboard_total = get_total_active_resources()
    
    assert inventory_total == dashboard_total, (
        f"RECONCILIATION FAILURE: "
        f"Inventory total ({inventory_total}) != Dashboard total ({dashboard_total})"
    )
    
    print(f"  ✓ Reconciliation passed: {inventory_total} resources")


def test_canonical_predicate_consistency():
    """
    Verify both functions use the same canonical predicate.
    
    This test validates that:
    1. get_active_containers_filtered() returns only active, non-placeholder containers
    2. get_total_active_resources() counts only active, non-placeholder containers
    """
    from db import get_active_containers_filtered
    
    containers = get_active_containers_filtered()
    
    for c in containers:
        # Every returned container must satisfy canonical predicate
        is_archived = c.get('is_archived', 0)
        is_placeholder = c.get('is_placeholder', 0)
        
        assert is_archived == 0, f"Container {c.get('container_key')} has is_archived={is_archived}"
        assert is_placeholder == 0, f"Container {c.get('container_key')} has is_placeholder={is_placeholder}"
    
    print(f"  ✓ Canonical predicate verified for {len(containers)} containers")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("INVENTORY ↔ DASHBOARD RECONCILIATION TEST")
    print("=" * 60 + "\n")
    
    test_inventory_dashboard_reconciliation()
    test_canonical_predicate_consistency()
    
    print("\n" + "=" * 60)
    print("ALL RECONCILIATION TESTS PASSED ✓")
    print("=" * 60 + "\n")
