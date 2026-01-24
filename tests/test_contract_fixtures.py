"""
Contract Tests Using Fixture Dataset
=====================================
SAFETY ENFORCEMENT (CRITICAL - RUNS BEFORE ANY IMPORTS):
1. Read TEST_DATABASE_URL (fail if missing)
2. Set DATABASE_URL = TEST_DATABASE_URL (before ANY db imports)
3. Verify override worked

This prevents db.py from connecting to production.
"""

import os
import sys
from pathlib import Path

# =============================================================================
# PHASE 1: ENFORCE TEST_DATABASE_URL (BEFORE ANY APP IMPORTS)
# =============================================================================

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    print("\n" + "=" * 70, file=sys.stderr)
    print("ERROR: TEST_DATABASE_URL is required", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("\nContract tests require an isolated test database.", file=sys.stderr)
    print("Set TEST_DATABASE_URL to a dedicated test PostgreSQL instance.", file=sys.stderr)
    print("\nExample:", file=sys.stderr)
    print("  export TEST_DATABASE_URL='postgresql://user:pass@localhost:5432/tcm_test'", file=sys.stderr)
    print("\nTests will NOT run against DATABASE_URL to prevent production writes.", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)
    sys.exit(1)

# Override DATABASE_URL BEFORE any imports
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Verify override worked
assert os.environ.get("DATABASE_URL") == TEST_DATABASE_URL, \
    "DATABASE_URL override failed - tests cannot proceed safely"

# =============================================================================
# PHASE 2: NOW SAFE TO IMPORT APP MODULES
# =============================================================================

import pytest

from services.container_service import import_from_folder
from services.kpi_service import get_submission_summary
from db import (
    get_active_containers,
    clear_containers,
    update_container_scrub,
    update_container_invest,
    get_all_containers,
    init_db
)


# =============================================================================
# Pytest Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def clean_db():
    """
    Ensure clean database state before each test.
    
    ISOLATION: Truncates tables in TEST_DATABASE_URL.
    NOT PARALLEL-SAFE: Tests must run serially (pytest -n 0).
    """
    init_db()
    clear_containers()
    yield
    clear_containers()


@pytest.fixture
def fixture_path():
    """
    Get base fixture path with STRICT validation.
    
    Guards:
    1. Path must be under tests/fixtures/ (anchored check)
    2. Path must NOT contain "Payroc Training Catalogue"
    """
    # Get repo root (2 levels up from this file)
    repo_root = Path(__file__).resolve().parents[1]
    fixtures_root = repo_root / "tests" / "fixtures"
    
    # Construct path
    path = Path(__file__).parent / "fixtures" / "demo_catalog"
    
    # STRICT GUARD 1: Must be under tests/fixtures/
    assert path.resolve().is_relative_to(fixtures_root.resolve()), \
        f"Fixture path must be under {fixtures_root}, got {path}"
    
    # STRICT GUARD 2: Must NOT contain production catalogue
    path_str = str(path.resolve()).lower()
    assert "payroc training catalogue" not in path_str, \
        f"Must NOT use Payroc Training Catalogue: {path}"
    
    return str(path)


# =============================================================================
# Test 1: Reconciliation
# =============================================================================

def test_reconciliation_dashboard_equals_inventory(clean_db, fixture_path):
    """Dashboard total must equal Inventory total."""
    import_from_folder(fixture_path)
    
    containers = get_active_containers()
    inventory_total = sum(c.get("resource_count", 0) for c in containers)
    
    summary = get_submission_summary()
    dashboard_total = summary["total"]
    
    assert dashboard_total == inventory_total, \
        f"Reconciliation failure: Dashboard={dashboard_total}, Inventory={inventory_total}"
    assert dashboard_total > 0


# =============================================================================
# Test 2: links.txt Parsing
# =============================================================================

def test_links_parsing_counts_exactly_2_valid_urls(clean_db, fixture_path):
    """Exactly 2 valid URLs counted from links.txt."""
    import_from_folder(fixture_path)
    
    containers = get_active_containers()
    link_containers = [c for c in containers if c.get("container_type") == "link"]
    
    assert len(link_containers) == 2, \
        f"Expected 2 link containers, got {len(link_containers)}"
    
    for link in link_containers:
        assert link.get("resource_count") == 1
    
    urls = [c.get("web_url") or c.get("display_name") for c in link_containers]
    assert "https://example.com/a" in urls
    assert "http://example.com/b" in urls
    
    link_total = sum(c.get("resource_count", 0) for c in link_containers)
    assert link_total == 2


# =============================================================================
# Test 3: Archive/Reactivation
# =============================================================================

def test_archive_reactivation_preserves_decisions(clean_db):
    """Decisions survive archive → reappear cycle."""
    repo_root = Path(__file__).resolve().parents[1]
    fixtures_root = repo_root / "tests" / "fixtures"
    
    test_dir = Path(__file__).parent
    v1_path = test_dir / "fixtures" / "demo_catalog_v1"
    v2_path = test_dir / "fixtures" / "demo_catalog_v2"
    v3_path = test_dir / "fixtures" / "demo_catalog_v3"
    
    # Validate all paths
    for path in [v1_path, v2_path, v3_path]:
        assert path.resolve().is_relative_to(fixtures_root.resolve()), \
            f"Path must be under tests/fixtures/: {path}"
        assert "payroc training catalogue" not in str(path).lower(), \
            f"Must NOT use production catalogue: {path}"
    
    # Phase 1: Sync v1, write decisions
    import_from_folder(str(v1_path))
    
    containers = get_active_containers()
    file_one = next((c for c in containers if "file_one.pdf" in c.get("relative_path", "")), None)
    assert file_one is not None
    
    container_key = file_one["container_key"]
    
    update_container_scrub(container_key, "Include", "test", "Test note")
    update_container_invest(container_key, "High", "test", "2w", "Test invest")
    
    # Phase 2: Sync v2 (file removed), verify archived
    import_from_folder(str(v2_path))
    
    all_containers = get_all_containers()
    file_archived = next((c for c in all_containers if c["container_key"] == container_key), None)
    assert file_archived is not None
    assert file_archived["is_archived"] == 1
    
    active = get_active_containers()
    assert not any(c["container_key"] == container_key for c in active)
    
    # Phase 3: Sync v3 (file returns), verify decisions intact
    import_from_folder(str(v3_path))
    
    all_after_v3 = get_all_containers()
    file_reactivated = next((c for c in all_after_v3 if c["container_key"] == container_key), None)
    assert file_reactivated is not None
    assert file_reactivated["is_archived"] == 0
    assert file_reactivated["scrub_status"] == "Include"
    assert file_reactivated["scrub_notes"] == "Test note"
    assert file_reactivated["invest_decision"] == "High"
    assert file_reactivated["invest_notes"] == "Test invest"
