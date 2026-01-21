"""
Test OS Artifact Exclusion
==========================
Asserts that OS metadata files are never ingested as resources.

Run: pytest tests/test_os_artifact_exclusion.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.container_service import EXCLUDED_FILENAMES


def test_desktop_ini_in_denylist():
    """desktop.ini must be in the exclusion set."""
    assert "desktop.ini" in EXCLUDED_FILENAMES


def test_ds_store_in_denylist():
    """.ds_store must be in the exclusion set (lowercase)."""
    assert ".ds_store" in EXCLUDED_FILENAMES


def test_thumbs_db_in_denylist():
    """thumbs.db must be in the exclusion set (lowercase)."""
    assert "thumbs.db" in EXCLUDED_FILENAMES


def test_exclusion_is_case_insensitive():
    """Comparison must work case-insensitively via .lower()."""
    assert "Desktop.INI".lower() in EXCLUDED_FILENAMES
    assert ".DS_Store".lower() in EXCLUDED_FILENAMES
    assert "THUMBS.DB".lower() in EXCLUDED_FILENAMES


if __name__ == "__main__":
    test_desktop_ini_in_denylist()
    test_ds_store_in_denylist()
    test_thumbs_db_in_denylist()
    test_exclusion_is_case_insensitive()
    print("All OS artifact exclusion tests passed.")
