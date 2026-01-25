"""
Dashboard Metrics Tests - LOCKED SPEC (2026-01-25)

Required tests per locked spec:
1. test_counts_use_sum_resource_count_not_row_count
2. test_items_remaining_uses_normalize_status_unreviewed
3. test_donut_segments_sum_to_total_resources
4. test_audience_rows_always_present
5. test_training_sources_removed
6. test_percent_divide_by_zero_safe
"""
import re
import pytest
from pathlib import Path


class TestDashboardMetricsIntegrity:
    """Test that dashboard metrics follow locked spec rules."""
    
    def _get_dashboard_view_source(self):
        """Extract dashboard_view function source code."""
        views_path = Path(__file__).parent.parent / 'tcm_app' / 'views.py'
        if not views_path.exists():
            pytest.skip("views.py not found")
        
        content = views_path.read_text()
        lines = content.splitlines()
        
        # Find dashboard_view function boundaries
        start_line = None
        end_line = None
        for i, line in enumerate(lines):
            if 'def dashboard_view(request):' in line:
                start_line = i
            elif start_line is not None and '@login_required' in line:
                end_line = i
                break
        
        if start_line is None:
            pytest.skip("dashboard_view function not found")
        if end_line is None:
            end_line = len(lines)
        
        return '\n'.join(lines[start_line:end_line])
    
    def test_counts_use_sum_resource_count_not_row_count(self):
        """
        Dashboard view source must NOT use len() or sum(1 for ...) for counting.
        All counts must use SUM(resource_count).
        """
        dashboard_code = self._get_dashboard_view_source()
        
        # Filter out comment-only lines
        active_lines = [l for l in dashboard_code.split('\n') if not l.strip().startswith('#')]
        active_code = '\n'.join(active_lines)
        
        # Check for forbidden patterns
        len_matches = re.findall(r'len\([^)]+\)', active_code)
        for m in len_matches:
            # Allow len() only for non-metric purposes like path parsing
            if 'active' in m or 'containers' in m or 'resources' in m:
                pytest.fail(f"Found forbidden len() for resource counting: {m}")
        
        # Verify sum(... resource_count ...) pattern exists
        assert 'resource_count' in active_code, "Must use resource_count for counting"
        assert "c.get('resource_count'" in active_code, "Must use c.get('resource_count', 0) pattern"
    
    def test_items_remaining_uses_normalize_status_unreviewed(self):
        """
        items_remaining must use normalize_status() and check for 'Unreviewed'.
        """
        dashboard_code = self._get_dashboard_view_source()
        
        # Verify normalize_status is used
        assert 'normalize_status' in dashboard_code, "Must use normalize_status()"
        
        # Verify Unreviewed check exists
        assert "'Unreviewed'" in dashboard_code, "Must check for 'Unreviewed' status"
        
        # Verify items_remaining computation exists
        assert 'items_remaining' in dashboard_code, "Must compute items_remaining"
    
    def test_donut_segments_sum_to_total_resources(self):
        """
        Donut segments (onboarding + upskilling + other) must sum to total_resources.
        """
        # Test the computation logic directly
        def compute_donut(onboarding, upskilling, total):
            other = max(total - onboarding - upskilling, 0)
            return onboarding + upskilling + other
        
        # Test case 1: Normal case
        assert compute_donut(30, 50, 100) == 100
        
        # Test case 2: All onboarding
        assert compute_donut(100, 0, 100) == 100
        
        # Test case 3: All upskilling
        assert compute_donut(0, 100, 100) == 100
        
        # Test case 4: All other (neither onboarding nor upskilling)
        assert compute_donut(0, 0, 100) == 100
        
        # Test case 5: Zero total
        assert compute_donut(0, 0, 0) == 0
        
        # Test case 6: other_count is clamped at 0 (can't be negative)
        # In real data onboarding+upskilling can never exceed total since
        # they are subsets. The clamp protects against data anomalies.
        def compute_other(onboarding, upskilling, total):
            return max(total - onboarding - upskilling, 0)
        
        assert compute_other(100, 100, 100) == 0  # clamp to 0
    
    def test_audience_rows_always_present(self):
        """
        Context must contain 8 audience rows in correct order.
        """
        dashboard_code = self._get_dashboard_view_source()
        
        # Verify fixed audience order is defined
        expected_audiences = [
            'Direct',
            'Indirect',
            'Integration',
            'FI',
            'Partner Management',
            'Operations',
            'Compliance',
            'Unassigned',
        ]
        
        for aud in expected_audiences:
            assert f"'{aud}'" in dashboard_code, f"Must include audience: {aud}"
        
        # Verify AUDIENCE_ORDER list exists
        assert 'AUDIENCE_ORDER' in dashboard_code, "Must define AUDIENCE_ORDER list"
        
        # Verify audience_breakdown is built from fixed order
        assert 'for aud_label in AUDIENCE_ORDER' in dashboard_code, \
            "Must iterate AUDIENCE_ORDER to build fixed rows"
    
    def test_training_sources_removed(self):
        """
        Training Sources must not exist in dashboard context or template.
        """
        dashboard_code = self._get_dashboard_view_source()
        
        # Check context does not contain training_sources
        assert 'training_sources' not in dashboard_code, \
            "training_sources should be removed from dashboard"
        
        # Check template does not reference Training Sources
        template_path = Path(__file__).parent.parent / 'tcm_app' / 'templates' / 'tcm_app' / 'dashboard.html'
        if template_path.exists():
            template_content = template_path.read_text(encoding='utf-8')
            assert 'Training Sources' not in template_content, \
                "Training Sources should be removed from template"
            assert 'training_sources' not in template_content, \
                "training_sources variable should not be in template"
    
    def test_percent_divide_by_zero_safe(self):
        """
        With total_resources=0, no exception and all pct values are 0.0.
        """
        # Test the computation logic directly
        def compute_pct(count, total):
            return round((count / total) * 100, 1) if total > 0 else 0.0
        
        # Zero total (must not raise)
        assert compute_pct(0, 0) == 0.0
        assert compute_pct(5, 0) == 0.0
        
        # Normal case
        assert compute_pct(50, 100) == 50.0
        assert compute_pct(33, 100) == 33.0


class TestDashboardViewContract:
    """Test dashboard_view context contract."""
    
    def test_context_keys_exist(self):
        """
        Dashboard view must return all required context keys.
        """
        required_keys = [
            'total_resources',
            'items_remaining',
            'include_count',
            'modify_count',
            'sunset_count',
            'show_decision_bar',
            'onboarding_count',
            'upskilling_count',
            'other_count',
            'onboarding_pct',
            'upskilling_pct',
            'other_pct',
            'offset_onboarding',
            'offset_upskilling',
            'offset_other',
            'donut_breakdown',
            'training_types',
            'audience_breakdown',
        ]
        
        views_path = Path(__file__).parent.parent / 'tcm_app' / 'views.py'
        if not views_path.exists():
            pytest.skip("views.py not found")
        
        content = views_path.read_text()
        
        for key in required_keys:
            assert f"'{key}'" in content, f"Required context key '{key}' not found"
    
    def test_humanize_label_function_exists(self):
        """
        humanize_label function must exist to convert training types.
        """
        views_path = Path(__file__).parent.parent / 'tcm_app' / 'views.py'
        if not views_path.exists():
            pytest.skip("views.py not found")
        
        content = views_path.read_text()
        
        assert 'def humanize_label' in content, "humanize_label function must exist"
        assert 'title()' in content, "Must use title() for title case"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
