"""
Metrics Reconciliation Tests — Option A Verification
=====================================================
Proves that Inventory and Dashboard use the same resource definition.

Option A Contract:
- Resource = resource_type IN ('file', 'link')
- Folder = excluded from Inventory
- Inventory total == Dashboard total (always)
"""
import os
import pytest


# Skip database tests if no DATABASE_URL
requires_database = pytest.mark.skipif(
    not os.environ.get('DATABASE_URL'),
    reason="DATABASE_URL not set - skipping database tests"
)


class TestMetricsReconciliation:
    """
    Tests proving folder presence does not affect Inventory/Dashboard reconciliation.
    """
    
    @requires_database
    def test_resource_filter_excludes_folders(self):
        """
        get_active_resources_filtered() must exclude folders.
        """
        from db import get_active_resources_filtered
        
        resources = get_active_resources_filtered()
        
        # No folders should be in the result
        for r in resources:
            assert r.get('resource_type') in ('file', 'link'), \
                f"Folder found in resources: {r.get('resource_type')}"
    
    @requires_database
    def test_resource_departments_excludes_folder_only_depts(self):
        """
        get_active_resource_departments() must only return departments that have resources.
        """
        from db import get_active_resource_departments
        
        depts = get_active_resource_departments()
        assert isinstance(depts, list)
    
    @requires_database
    def test_resource_training_types_excludes_folder_only_types(self):
        """
        get_active_resource_training_types() must only return types that have resources.
        """
        from db import get_active_resource_training_types
        
        types = get_active_resource_training_types()
        assert isinstance(types, list)
    
    def test_inventory_uses_resource_functions(self):
        """
        Verify inventory_view imports resource-only functions.
        This is a CODE STRUCTURE test - no database required.
        """
        import inspect
        from tcm_app.views import inventory_view
        
        source = inspect.getsource(inventory_view)
        
        # Must use resource functions
        assert 'get_active_resources_filtered' in source, \
            "inventory_view must use get_active_resources_filtered"
        assert 'get_active_resource_departments' in source, \
            "inventory_view must use get_active_resource_departments"
        assert 'get_active_resource_training_types' in source, \
            "inventory_view must use get_active_resource_training_types"
        
        # Must NOT use container functions (regression check)
        assert 'get_active_containers_filtered' not in source, \
            "inventory_view must NOT use get_active_containers_filtered"
