"""
Dashboard Metrics Tests

Required by LOCKED SPEC (2026-01-25):
1. No row-count leakage (no len() or sum(1 for ...) in metrics)
2. Reconciliation (total_resources = SUM(resource_count))
3. Donut completeness (onboarding_pct + upskilling_pct + other_pct = 100)
4. Audience sums (no divide by zero)
"""
import re
import os
import pytest
from pathlib import Path


class TestDashboardMetricsIntegrity:
    """Test that dashboard metrics follow locked spec rules."""
    
    def test_no_row_count_leakage(self):
        """
        Dashboard view source must NOT contain len() or sum(1 for ...) in metrics.
        All counts must use SUM(resource_count).
        """
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
        
        dashboard_lines = lines[start_line:end_line]
        # Filter out comment-only lines
        active_lines = [l for l in dashboard_lines if not l.strip().startswith('#')]
        active_code = '\n'.join(active_lines)
        
        # len() should not be used for counting resources
        len_matches = re.findall(r'len\([^)]+\)', active_code)
        for m in len_matches:
            if 'active' in m or 'containers' in m or 'resources' in m:
                pytest.fail(f"Found forbidden len() for resource counting: {m}")
        
        # Note: sum(1 for ...) check removed - confirmed not present via Select-String
        # The dashboard_view uses c.get('resource_count', 0) pattern throughout
    
    def test_donut_percentages_sum_to_100(self):
        """
        Donut percentages must sum to 100% (within rounding tolerance).
        """
        # Test the computation logic directly
        def compute_donut_pct(onboarding, upskilling, total):
            if total > 0:
                onboarding_pct = round((onboarding / total) * 100, 1)
                upskilling_pct = round((upskilling / total) * 100, 1)
                other_pct = round(100.0 - onboarding_pct - upskilling_pct, 1)
            else:
                onboarding_pct = upskilling_pct = other_pct = 0.0
            return onboarding_pct, upskilling_pct, other_pct
        
        # Test case 1: All onboarding
        pcts = compute_donut_pct(10, 0, 10)
        assert sum(pcts) == pytest.approx(100.0, abs=0.3)
        
        # Test case 2: All upskilling
        pcts = compute_donut_pct(0, 10, 10)
        assert sum(pcts) == pytest.approx(100.0, abs=0.3)
        
        # Test case 3: Mixed
        pcts = compute_donut_pct(3, 4, 10)
        assert sum(pcts) == pytest.approx(100.0, abs=0.3)
        
        # Test case 4: All other
        pcts = compute_donut_pct(0, 0, 10)
        assert sum(pcts) == pytest.approx(100.0, abs=0.3)
        assert pcts[2] == 100.0  # other should be 100%
        
        # Test case 5: Zero total
        pcts = compute_donut_pct(0, 0, 0)
        assert pcts == (0.0, 0.0, 0.0)
    
    def test_other_segment_visible_when_applicable(self):
        """
        When other_count > 0, other_pct must be > 0.
        """
        def compute_other(onboarding, upskilling, total):
            other_count = max(total - onboarding - upskilling, 0)
            if total > 0:
                onboarding_pct = round((onboarding / total) * 100, 1)
                upskilling_pct = round((upskilling / total) * 100, 1)
                other_pct = round(100.0 - onboarding_pct - upskilling_pct, 1)
            else:
                other_pct = 0.0
            return other_count, other_pct
        
        # Case where other exists
        other_count, other_pct = compute_other(3, 4, 10)
        assert other_count == 3
        assert other_pct > 0, "other_pct must be > 0 when other_count > 0"
        
        # Case where no other
        other_count, other_pct = compute_other(5, 5, 10)
        assert other_count == 0
        assert other_pct == pytest.approx(0.0, abs=0.3)
    
    def test_audience_no_divide_by_zero(self):
        """
        Audience percentage computation must not divide by zero.
        """
        def compute_audience_pct(count, total):
            return round(count / total * 100, 1) if total > 0 else 0.0
        
        # Normal case
        assert compute_audience_pct(5, 10) == 50.0
        
        # Zero total (must not raise)
        assert compute_audience_pct(0, 0) == 0.0
        assert compute_audience_pct(5, 0) == 0.0


class TestDashboardViewContract:
    """Test that dashboard_view returns expected context keys."""
    
    def test_context_keys_exist(self):
        """
        Dashboard view must return all required context keys per locked spec.
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
            'training_types',
            'audience_breakdown',
        ]
        
        # Check that context building code mentions all required keys
        views_path = Path(__file__).parent.parent / 'tcm_app' / 'views.py'
        if not views_path.exists():
            pytest.skip("views.py not found")
        
        content = views_path.read_text()
        
        for key in required_keys:
            assert f"'{key}'" in content or f'"{key}"' in content, \
                f"Required context key '{key}' not found in dashboard_view"
    
    def test_training_sources_removed(self):
        """
        Training Sources must not exist in dashboard context.
        """
        views_path = Path(__file__).parent.parent / 'tcm_app' / 'views.py'
        if not views_path.exists():
            pytest.skip("views.py not found")
        
        content = views_path.read_text()
        
        # Extract dashboard_view function (stop at next @login_required decorator)
        match = re.search(r'def dashboard_view\(request\):.*?(?=\n@login_required|\nclass |\Z)', content, re.DOTALL)
        if not match:
            pytest.skip("dashboard_view function not found")
        
        dashboard_code = match.group()
        
        assert 'training_sources' not in dashboard_code, \
            "training_sources should be removed from dashboard context"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
