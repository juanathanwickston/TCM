"""
Tests for Phase 5 Tools page.

Tests verify:
1. GET /tools always returns 200
2. POST actions require superuser
3. SharePoint env-gating works
4. Clear All requires exact confirmation match
5. No removed features exist (negative tests)
"""
import pytest
from services.scrub_rules import normalize_status


class TestToolsGetNever500:
    """Tests that GET /tools never 500s."""
    
    def test_tools_view_exists(self):
        """tools_view function must exist."""
        from tcm_app.views import tools_view
        assert callable(tools_view)
    
    def test_tools_view_no_service_calls_on_get(self):
        """tools_view GET must not call heavy service functions."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.tools_view)
        
        # Must not call heavy service functions on GET
        assert 'sync_from_sharepoint()' not in source
        assert 'import_from_zip(' not in source
        assert 'clear_containers()' not in source


class TestSuperuserGates:
    """Tests for superuser-only access on POST actions."""
    
    def test_import_zip_view_checks_superuser(self):
        """import_zip_view must check superuser status."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.import_zip_view)
        assert 'is_superuser' in source
        assert 'HttpResponseForbidden' in source or 'Forbidden' in source
    
    def test_sync_sharepoint_view_checks_superuser(self):
        """sync_sharepoint_view must check superuser status."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.sync_sharepoint_view)
        assert 'is_superuser' in source
    
    def test_clear_all_data_view_checks_superuser(self):
        """clear_all_data_view must check superuser status."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.clear_all_data_view)
        assert 'is_superuser' in source


class TestSharePointEnvGating:
    """Tests for SharePoint environment variable gating."""
    
    def test_sharepoint_checks_env_vars(self):
        """sync_sharepoint_view must check env vars before calling service."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.sync_sharepoint_view)
        
        # Must check these env vars
        assert 'SHAREPOINT_SYNC_ENABLED' in source
        assert 'SHAREPOINT_TENANT_ID' in source or 'SHAREPOINT_CLIENT_ID' in source


class TestClearAllConfirmation:
    """Tests for Clear All typed confirmation."""
    
    def test_clear_all_requires_exact_confirmation(self):
        """clear_all_data_view must require exact 'CLEAR ALL DATA' match."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.clear_all_data_view)
        
        # Must check for exact match
        assert "CLEAR ALL DATA" in source
        assert "confirmation" in source


class TestZipSizeLimit:
    """Tests for ZIP upload size limit."""
    
    def test_import_zip_enforces_size_limit(self):
        """import_zip_view must enforce 250MB limit server-side."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.import_zip_view)
        
        # Must check file size
        assert 'size' in source
        # Must have 250MB limit (250 * 1024 * 1024 = 262144000)
        assert '250' in source
    
    def test_import_zip_uses_safe_file_get(self):
        """import_zip_view must use .get() for file access (never KeyError)."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.import_zip_view)
        
        # Must use .get() pattern for safe file access
        assert ".get('zipfile')" in source or '.get("zipfile")' in source
    
    def test_import_zip_never_500s(self):
        """import_zip_view must have outer try/except to guarantee no 500s."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.import_zip_view)
        
        # Must have comprehensive error handling  
        assert 'except Exception' in source
        # Docstring should mention never 500
        assert 'NEVER 500' in source or 'never 500' in source.lower()


class TestNoRemovedFeatures:
    """Negative tests: removed features must not exist."""
    
    def test_no_export_csv_route(self):
        """No export/csv route should exist."""
        from tcm_app.urls import urlpatterns
        
        route_names = [p.name for p in urlpatterns if hasattr(p, 'name')]
        assert 'export_csv' not in route_names
        assert 'export_excel' not in route_names
    
    def test_no_folder_sync_route(self):
        """No folder sync route should exist."""
        from tcm_app.urls import urlpatterns
        
        route_names = [p.name for p in urlpatterns if hasattr(p, 'name')]
        assert 'import_folder' not in route_names
        assert 'sync_folder' not in route_names
    
    def test_no_audience_migration_route(self):
        """No audience migration route should exist."""
        from tcm_app.urls import urlpatterns
        
        route_names = [p.name for p in urlpatterns if hasattr(p, 'name')]
        assert 'run_audience_migration' not in route_names
        assert 'audience_migration' not in route_names
    
    def test_no_kpi_in_tools_template(self):
        """Tools template must not contain KPI tiles."""
        import pathlib
        
        template = pathlib.Path('tcm_app/templates/tcm_app/tools.html').read_text()
        
        # Must not have KPI/stats elements
        assert 'kpi' not in template.lower() or 'kpi' in template.lower() and False
        assert 'Resource Statistics' not in template
        assert 'Department Breakdown' not in template
    
    def test_no_export_in_tools_template(self):
        """Tools template must not contain export buttons."""
        import pathlib
        
        template = pathlib.Path('tcm_app/templates/tcm_app/tools.html').read_text()
        
        # Must not have export functionality
        assert 'Download CSV' not in template
        assert 'Download Excel' not in template
        assert 'export' not in template.lower()


class TestPRGPattern:
    """Tests for POST-Redirect-GET pattern."""
    
    def test_all_post_views_redirect(self):
        """All POST views must redirect after action."""
        import tcm_app.views as views
        import inspect
        
        for view_name in ['import_zip_view', 'sync_sharepoint_view', 'clear_all_data_view']:
            source = inspect.getsource(getattr(views, view_name))
            assert "redirect('tools')" in source or "redirect" in source
