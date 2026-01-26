"""
Audience Single Source of Truth Test
=====================================
Verifies that Dashboard uses CANONICAL_AUDIENCES, not a hardcoded list.
This prevents audience mismatch between Inventory and Dashboard.
"""


class TestAudienceSingleSource:
    """
    Tests proving Dashboard uses CANONICAL_AUDIENCES as single source of truth.
    """
    
    def test_dashboard_imports_canonical_audiences(self):
        """
        Dashboard view must import CANONICAL_AUDIENCES from scrub_rules.py.
        This is a CODE STRUCTURE test - no database required.
        """
        import inspect
        from tcm_app.views import dashboard_view
        
        source = inspect.getsource(dashboard_view)
        
        # Must import CANONICAL_AUDIENCES
        assert 'CANONICAL_AUDIENCES' in source, \
            "dashboard_view must import CANONICAL_AUDIENCES from scrub_rules"
        
        # Should NOT have hardcoded list (regression check)
        # Look for pattern that indicates a hardcoded list of audiences
        assert "'Direct'," not in source, \
            "dashboard_view must NOT hardcode 'Direct' - use CANONICAL_AUDIENCES"
        assert "'Indirect'," not in source, \
            "dashboard_view must NOT hardcode 'Indirect' - use CANONICAL_AUDIENCES"
    
    def test_canonical_audiences_contains_required_values(self):
        """
        CANONICAL_AUDIENCES must contain all required audience values.
        """
        from services.scrub_rules import CANONICAL_AUDIENCES
        
        required = ['Direct Sales', 'Indirect Sales', 'Integration', 'FI', 
                    'Partner Management', 'Operations', 'Compliance', 'POS']
        
        for aud in required:
            assert aud in CANONICAL_AUDIENCES, \
                f"CANONICAL_AUDIENCES missing required value: {aud}"
    
    def test_inventory_uses_canonical_audiences(self):
        """
        Inventory view must use CANONICAL_AUDIENCES for dropdown.
        """
        import inspect
        from tcm_app.views import inventory_view
        
        source = inspect.getsource(inventory_view)
        
        # Inventory should import CANONICAL_AUDIENCES
        assert 'CANONICAL_AUDIENCES' in source, \
            "inventory_view must import CANONICAL_AUDIENCES"
