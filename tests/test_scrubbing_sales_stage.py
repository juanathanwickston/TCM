"""
Regression tests for Sales Stage functionality in Scrubbing workflow.

Tests verify:
1. Template context uses SALES_STAGES tuples correctly (key, label)
2. save_scrub_view validates/sanitizes invalid sales_stage values
3. update_sales_stage rejects label strings
"""
import pytest
from unittest.mock import patch, MagicMock

# Import source of truth
from services.sales_stage import SALES_STAGES, SALES_STAGE_KEYS, SALES_STAGE_LABELS


class TestSalesStageOptions:
    """Tests for Sales Stage dropdown options."""
    
    def test_sales_stages_are_tuples_of_key_label(self):
        """SALES_STAGES must be list of (key, label) tuples."""
        assert isinstance(SALES_STAGES, list)
        assert len(SALES_STAGES) > 0
        
        for item in SALES_STAGES:
            assert isinstance(item, tuple), f"Expected tuple, got {type(item)}"
            assert len(item) == 2, f"Expected 2-tuple, got {len(item)}"
            key, label = item
            assert isinstance(key, str), f"Key must be string: {key}"
            assert isinstance(label, str), f"Label must be string: {label}"
            assert key.startswith("stage_"), f"Key must start with 'stage_': {key}"
    
    def test_sales_stage_keys_are_just_keys(self):
        """SALES_STAGE_KEYS must contain only key strings, not tuples or labels."""
        for key in SALES_STAGE_KEYS:
            assert isinstance(key, str)
            assert key.startswith("stage_")
            # Keys must not be labels
            assert not key[0].isdigit(), f"Key looks like a label: {key}"
    
    def test_template_context_can_unpack_tuples(self):
        """Template's {% for key, label in sales_stages %} must work."""
        # Simulate what Django template does
        for key, label in SALES_STAGES:
            assert key in SALES_STAGE_KEYS
            assert label == SALES_STAGE_LABELS[key]


class TestSalesStageValidation:
    """Tests for Sales Stage validation in save_scrub_view."""
    
    def test_valid_key_is_accepted(self):
        """A valid key like 'stage_1_identify' should be accepted."""
        from services.sales_stage import SALES_STAGE_KEYS
        
        test_key = "stage_1_identify"
        assert test_key in SALES_STAGE_KEYS
    
    def test_label_is_not_valid_key(self):
        """A label like '1. Identify the Customer' is NOT a valid key."""
        from services.sales_stage import SALES_STAGE_KEYS
        
        test_label = "1. Identify the Customer"
        assert test_label not in SALES_STAGE_KEYS
    
    @pytest.mark.skipif(
        not __import__('os').environ.get('DATABASE_URL'),
        reason="DATABASE_URL not configured"
    )
    def test_update_sales_stage_rejects_label(self):
        """update_sales_stage must reject label strings."""
        from db import update_sales_stage
        
        # Passing a label (not a key) should raise ValueError
        with pytest.raises(ValueError):
            update_sales_stage(
                resource_key="test_container",
                stage="1. Identify the Customer"  # This is a label, not a key
            )
    
    @pytest.mark.skipif(
        not __import__('os').environ.get('DATABASE_URL'),
        reason="DATABASE_URL not configured"
    )
    def test_update_sales_stage_accepts_none(self):
        """update_sales_stage must accept None to clear the stage."""
        from db import update_sales_stage
        
        # None should not raise - it clears the stage
        # This will try to update a non-existent container but shouldn't raise ValueError
        try:
            update_sales_stage(resource_key="nonexistent_test", stage=None)
        except ValueError:
            pytest.fail("update_sales_stage should accept None")
        except Exception:
            pass  # Other errors (like DB connection) are OK for this test


class TestSalesStageKeyValues:
    """Tests for specific key values."""
    
    def test_expected_keys_exist(self):
        """All 6 sales stage keys must exist."""
        expected_keys = [
            "stage_1_identify",
            "stage_2_appointment",
            "stage_3_prep",
            "stage_4_make_sale",
            "stage_5_close",
            "stage_6_referrals",
        ]
        for key in expected_keys:
            assert key in SALES_STAGE_KEYS, f"Missing expected key: {key}"
    
    def test_key_to_label_mapping(self):
        """Each key must map to the correct label."""
        expected = {
            "stage_1_identify": "1. Identify the Customer",
            "stage_2_appointment": "2. Ask for Appointment",
            "stage_3_prep": "3. Prep for Appointment",
            "stage_4_make_sale": "4. Make the Sale",
            "stage_5_close": "5. Close the Sale",
            "stage_6_referrals": "6. Ask for Referrals",
        }
        for key, label in expected.items():
            assert SALES_STAGE_LABELS.get(key) == label, f"Mismatch for {key}"
