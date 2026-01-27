"""
Tests for compute_file_count() and Inventory Totals Integrity
=============================================================

Gate tests that must pass before UI implementation.
"""

import sys
sys.path.insert(0, '.')

# =============================================================================
# A) Unit tests for compute_file_count(container)
# =============================================================================

def test_file_always_counts_as_1():
    """File always counts as 1."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "file"})
    assert result == 1, f"Expected 1, got {result}"
    print("  PASS: File counts as 1")


def test_folder_uses_contents_count():
    """Folder uses contents_count."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "folder", "contents_count": 7})
    assert result == 7, f"Expected 7, got {result}"
    print("  PASS: Folder uses contents_count")


def test_folder_null_contents_count_fails_closed():
    """Folder NULL contents_count fails closed to 0."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "folder", "contents_count": None})
    assert result == 0, f"Expected 0, got {result}"
    print("  PASS: Folder NULL contents_count -> 0")


def test_folder_missing_contents_count_fails_closed():
    """Folder missing contents_count fails closed to 0."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "folder"})
    assert result == 0, f"Expected 0, got {result}"
    print("  PASS: Folder missing contents_count -> 0")


def test_folder_negative_contents_count_clamps():
    """Folder negative contents_count clamps to 0."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "folder", "contents_count": -3})
    assert result == 0, f"Expected 0, got {result}"
    print("  PASS: Folder negative contents_count -> 0")


def test_link_uses_valid_link_count():
    """Link uses valid_link_count."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "link", "valid_link_count": 4})
    assert result == 4, f"Expected 4, got {result}"
    print("  PASS: Link uses valid_link_count")


def test_links_plural_uses_valid_link_count():
    """Links (plural) also uses valid_link_count."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "links", "valid_link_count": 2})
    assert result == 2, f"Expected 2, got {result}"
    print("  PASS: Links (plural) uses valid_link_count")


def test_link_null_valid_link_count_fails_closed():
    """Link NULL valid_link_count fails closed to 0."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "link", "valid_link_count": None})
    assert result == 0, f"Expected 0, got {result}"
    print("  PASS: Link NULL valid_link_count -> 0")


def test_unknown_resource_type_fails_closed():
    """Unknown resource_type fails closed to 0."""
    from services.container_service import compute_file_count
    result = compute_file_count({"resource_type": "weird"})
    assert result == 0, f"Expected 0, got {result}"
    print("  PASS: Unknown resource_type -> 0")


def test_non_numeric_counts_do_not_crash():
    """Non-numeric counts are converted, or fail closed to 0."""
    from services.container_service import compute_file_count
    
    # String numeric should convert
    result = compute_file_count({"resource_type": "folder", "contents_count": "5"})
    assert result == 5, f"Expected 5, got {result}"
    
    result = compute_file_count({"resource_type": "link", "valid_link_count": "3"})
    assert result == 3, f"Expected 3, got {result}"
    
    # Non-convertible string should fail closed to 0
    result = compute_file_count({"resource_type": "folder", "contents_count": "abc"})
    assert result == 0, f"Expected 0 for 'abc', got {result}"
    
    print("  PASS: Non-numeric counts handled correctly")


# =============================================================================
# B) Inventory totals integrity tests
# =============================================================================

def test_inventory_totals_with_fixture():
    """
    Verify primary and secondary totals are computed correctly from fixture.
    
    Fixture:
    - file A (resource_count=1)
    - folder B (resource_count=1, contents_count=10)
    - link C (resource_count=1, valid_link_count=3)
    - folder D (resource_count=1, contents_count=0)
    - unknown E (resource_count=1, no counts)
    
    Expected:
    - Primary (Total resources) = SUM(resource_count) = 5
    - Secondary (Items inside folders) = SUM(compute_file_count) = 14
    """
    from services.container_service import compute_file_count
    
    fixture = [
        {"resource_key": "A", "resource_type": "file", "resource_count": 1},
        {"resource_key": "B", "resource_type": "folder", "resource_count": 1, "contents_count": 10},
        {"resource_key": "C", "resource_type": "link", "resource_count": 1, "valid_link_count": 3},
        {"resource_key": "D", "resource_type": "folder", "resource_count": 1, "contents_count": 0},
        {"resource_key": "E", "resource_type": "weird", "resource_count": 1},
    ]
    
    # Primary total = SUM(resource_count)
    primary_total = sum(c.get("resource_count", 0) for c in fixture)
    assert primary_total == 5, f"Expected primary=5, got {primary_total}"
    
    # Secondary total = SUM(compute_file_count)
    secondary_total = sum(compute_file_count(c) for c in fixture)
    # file A = 1, folder B = 10, link C = 3, folder D = 0, unknown E = 0
    assert secondary_total == 14, f"Expected secondary=14, got {secondary_total}"
    
    print("  PASS: Inventory totals: primary=5, secondary=14")


def test_filter_consistency_same_dataset():
    """
    Apply a filter that removes folder B and link C.
    Both totals recompute from same filtered list.
    
    Remaining: file A, folder D, unknown E
    - Primary = 3
    - Secondary = 1 (file A only)
    """
    from services.container_service import compute_file_count
    
    fixture = [
        {"resource_key": "A", "resource_type": "file", "resource_count": 1},
        {"resource_key": "B", "resource_type": "folder", "resource_count": 1, "contents_count": 10},
        {"resource_key": "C", "resource_type": "link", "resource_count": 1, "valid_link_count": 3},
        {"resource_key": "D", "resource_type": "folder", "resource_count": 1, "contents_count": 0},
        {"resource_key": "E", "resource_type": "weird", "resource_count": 1},
    ]
    
    # Filter: exclude B and C
    filtered = [c for c in fixture if c["resource_key"] not in ("B", "C")]
    
    primary_total = sum(c.get("resource_count", 0) for c in filtered)
    assert primary_total == 3, f"Expected filtered primary=3, got {primary_total}"
    
    secondary_total = sum(compute_file_count(c) for c in filtered)
    # file A = 1, folder D = 0, unknown E = 0
    assert secondary_total == 1, f"Expected filtered secondary=1, got {secondary_total}"
    
    print("  PASS: Filter consistency: primary=3, secondary=1")


# =============================================================================
# Run all tests
# =============================================================================

def run_all_tests():
    print("\n" + "=" * 60)
    print("RUNNING INVENTORY TOTALS TEST SUITE")
    print("=" * 60 + "\n")
    
    print("A) Unit tests for compute_file_count:")
    test_file_always_counts_as_1()
    test_folder_uses_contents_count()
    test_folder_null_contents_count_fails_closed()
    test_folder_missing_contents_count_fails_closed()
    test_folder_negative_contents_count_clamps()
    test_link_uses_valid_link_count()
    test_links_plural_uses_valid_link_count()
    test_link_null_valid_link_count_fails_closed()
    test_unknown_resource_type_fails_closed()
    test_non_numeric_counts_do_not_crash()
    
    print("\nB) Inventory totals integrity tests:")
    test_inventory_totals_with_fixture()
    test_filter_consistency_same_dataset()
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_all_tests()
