"""
Test Metrics with Mock Data
============================
Tests resource counting logic with assertions.

Updated for 2-level structure (no department level in paths).

Run: python tests/test_metrics_mock.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    init_db, clear_containers, upsert_resource, make_resource_key,
    get_resource_totals, update_resource_scrub
)
from services.container_service import parse_path, parse_links_content, is_leaf_container


def test_path_parsing():
    """Test bucket/training_type extraction (4-level structure)."""
    print("Testing path parsing...")
    
    # Normal 4-level path: Dept/SubDept/Bucket/TrainingType
    result = parse_path("HR/_General/01_Onboarding/04_Video on Demand")
    assert result["bucket"] == "onboarding", f"Expected onboarding, got {result['bucket']}"
    assert result["primary_department"] == "HR", f"Expected HR dept, got {result['primary_department']}"
    assert result["sub_department"] == "_General", f"Expected _General sub_dept, got {result['sub_department']}"
    assert result["training_type"] == "video_on_demand", f"Expected video_on_demand, got {result['training_type']}"
    
    # Not Sure bucket (4-level)
    result = parse_path("POS/onePOS/03_Not Sure (Drop Here)/03_Self Directed")
    assert result["bucket"] == "not_sure", f"Expected not_sure, got {result['bucket']}"
    assert result["primary_department"] == "POS", f"Expected POS dept, got {result['primary_department']}"
    assert result["training_type"] == "self_directed", f"Expected self_directed, got {result['training_type']}"
    
    print("  PASS: Path parsing")


def test_links_parsing():
    """Test links.txt content parsing."""
    print("Testing links parsing...")
    
    # Valid links
    content = """
https://example.com/training1
# This is a comment
https://example.com/training2

http://legacy.example.com/old
    """
    result = parse_links_content(content)
    assert result["valid_link_count"] == 3, f"Expected 3 links, got {result['valid_link_count']}"
    assert result["is_placeholder"] == False
    assert result["resource_count"] == 3  # Each valid URL is 1 resource
    
    # Empty links
    empty_result = parse_links_content("")
    assert empty_result["valid_link_count"] == 0
    assert empty_result["is_placeholder"] == True
    assert empty_result["resource_count"] == 0
    
    # Only comments
    comment_result = parse_links_content("# No real links here\n# Just comments")
    assert comment_result["valid_link_count"] == 0
    assert comment_result["is_placeholder"] == True
    
    print("  PASS: Links parsing")


def test_leaf_detection():
    """Test container leaf detection rules (4-level structure)."""
    print("Testing leaf detection...")
    
    # File directly under L3 (Dept/SubDept/Bucket/TrainingType) → YES
    assert is_leaf_container(
        "HR/_General/01_Onboarding/04_Video on Demand",
        is_folder=False,
        filename="guide.pdf"
    ) == True, "File under L3 should be container"
    
    # Folder directly under L3 (L3+1 = L4) → YES
    assert is_leaf_container(
        "HR/_General/01_Onboarding/04_Video on Demand/onePOS Support",
        is_folder=True,
        filename="onePOS Support"
    ) == True, "Folder at L3+1 should be container"
    
    # L3 category folder → NO
    assert is_leaf_container(
        "HR/_General/01_Onboarding/04_Video on Demand",
        is_folder=True,
        filename="04_Video on Demand"
    ) == False, "L3 folder should not be container"
    
    # links.txt under L3 → YES
    assert is_leaf_container(
        "HR/_General/01_Onboarding/04_Video on Demand",
        is_folder=False,
        filename="links.txt"
    ) == True, "links.txt under L3 should be container"
    
    # Not Sure bucket (4-level)
    assert is_leaf_container(
        "POS/onePOS/03_Not Sure (Drop Here)/03_Self Directed",
        is_folder=False,
        filename="unsorted.pdf"
    ) == True, "File under Not Sure L3 should be container"
    
    print("  PASS: Leaf detection")


def test_resource_counting():
    """Test resource count aggregation with mock containers."""
    print("Testing resource counting...")
    
    # Clear and setup mock data
    clear_containers()
    
    # Onboarding / Video On Demand
    # - 2 files → should count 2
    upsert_resource(
        resource_key=make_resource_key(relative_path="01_Onboarding/04_Video on Demand/training1.pdf", resource_type="file"),
        relative_path="01_Onboarding/04_Video on Demand/training1.pdf",
        resource_type="file",
        bucket="onboarding",
        primary_department=None,  # Department assigned during scrubbing
        training_type="video_on_demand",
        display_name="training1.pdf",
        resource_count=1
    )
    upsert_resource(
        resource_key=make_resource_key(relative_path="01_Onboarding/04_Video on Demand/training2.pdf", resource_type="file"),
        relative_path="01_Onboarding/04_Video on Demand/training2.pdf",
        resource_type="file",
        bucket="onboarding",
        primary_department=None,
        training_type="video_on_demand",
        display_name="training2.pdf",
        resource_count=1
    )
    
    # - 1 folder container → should count 1
    upsert_resource(
        resource_key=make_resource_key(relative_path="01_Onboarding/04_Video on Demand/onePOS Support", resource_type="folder"),
        relative_path="01_Onboarding/04_Video on Demand/onePOS Support",
        resource_type="folder",
        bucket="onboarding",
        primary_department=None,
        training_type="video_on_demand",
        display_name="onePOS Support",
        resource_count=1
    )
    
    # - empty links.txt → should count 0
    upsert_resource(
        resource_key=make_resource_key(relative_path="01_Onboarding/04_Video on Demand/links.txt", resource_type="links"),
        relative_path="01_Onboarding/04_Video on Demand/links.txt",
        resource_type="links",
        bucket="onboarding",
        primary_department=None,
        training_type="video_on_demand",
        display_name="links.txt",
        resource_count=0,
        valid_link_count=0,
        is_placeholder=True
    )
    # Onboarding total = 2 + 1 + 0 = 3
    
    # Upskilling / Job Aids
    # - links.txt with URLs → count 1
    upsert_resource(
        resource_key=make_resource_key(relative_path="02_Upskilling/05_Job Aids/links.txt", resource_type="links"),
        relative_path="02_Upskilling/05_Job Aids/links.txt",
        resource_type="links",
        bucket="upskilling",
        primary_department=None,
        training_type="job_aids",
        display_name="links.txt",
        resource_count=1,
        valid_link_count=3,
        is_placeholder=False
    )
    # - 1 file → count 1
    upsert_resource(
        resource_key=make_resource_key(relative_path="02_Upskilling/05_Job Aids/guide.pdf", resource_type="file"),
        relative_path="02_Upskilling/05_Job Aids/guide.pdf",
        resource_type="file",
        bucket="upskilling",
        primary_department=None,
        training_type="job_aids",
        display_name="guide.pdf",
        resource_count=1
    )
    # Upskilling total = 2
    
    # Get totals
    totals = get_resource_totals()
    
    # Assert expected values
    assert totals["onboarding"] == 3, f"Expected onboarding=3, got {totals['onboarding']}"
    assert totals["upskilling"] == 2, f"Expected upskilling=2, got {totals['upskilling']}"
    
    print("  PASS: Resource counting")


def test_department_assignment():
    """Test that department is assigned during scrubbing, not from path."""
    print("Testing department assignment...")
    
    # Clear and add a container without department
    clear_containers()
    
    resource_key = make_resource_key(
        relative_path="01_Onboarding/03_Self Directed/test.pdf",
        resource_type="file"
    )
    upsert_resource(
        resource_key=resource_key,
        relative_path="01_Onboarding/03_Self Directed/test.pdf",
        resource_type="file",
        bucket="onboarding",
        primary_department=None,  # Not set from path
        training_type="self_directed",
        display_name="test.pdf",
        resource_count=1
    )
    
    # Assign audience during scrubbing (new signature: decision, no reasons for PASS)
    update_resource_scrub(
        resource_key=resource_key,
        decision="Include",  # Canonical scrub decision
        owner="Test User",
        notes=None,
        reasons=None,  # No reasons for PASS
        resource_count_override=None,
        audience="Operations"  # RENAMED from department
    )
    # Verify audience was set (audience is separate from primary_department)
    from db import get_audience_stats
    audience_stats = get_audience_stats()
    assert "Operations" in audience_stats, f"Audience should be in stats, got {audience_stats}"
    assert audience_stats["Operations"] == 1, f"Expected Operations=1, got {audience_stats.get('Operations')}"
    
    print("  PASS: Department assignment")


def test_deterministic_keys():
    """Test that container keys are stable across runs."""
    print("Testing deterministic keys...")
    
    key1 = make_resource_key(
        relative_path="01_Onboarding/04_Video on Demand/test.pdf",
        resource_type="file"
    )
    key2 = make_resource_key(
        relative_path="01_Onboarding/04_Video on Demand/test.pdf",
        resource_type="file"
    )
    assert key1 == key2, "Keys should be identical for same path"
    
    # Different type = different key
    key3 = make_resource_key(
        relative_path="01_Onboarding/04_Video on Demand/test.pdf",
        resource_type="folder"
    )
    assert key1 != key3, "Different types should produce different keys"
    
    # Case insensitive
    key4 = make_resource_key(
        relative_path="01_ONBOARDING/04_Video on Demand/test.pdf",
        resource_type="file"
    )
    assert key1 == key4, "Keys should be case-insensitive"
    
    print("  PASS: Deterministic keys")


def run_all_tests():
    """Run all tests with assertions."""
    print("\n" + "="*50)
    print("RUNNING METRICS TEST SUITE (2-LEVEL STRUCTURE)")
    print("="*50 + "\n")
    
    test_path_parsing()
    test_links_parsing()
    test_leaf_detection()
    test_resource_counting()
    test_department_assignment()
    test_deterministic_keys()
    
    print("\n" + "="*50)
    print("ALL TESTS PASSED")
    print("="*50 + "\n")


if __name__ == "__main__":
    run_all_tests()
