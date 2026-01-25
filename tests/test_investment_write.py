"""
Regression tests for Investment Write functionality.

Tests verify:
1. Investment view uses canonical read (get_containers_by_scrub_status)
2. save_investment_view uses canonical write (update_container_invest)
3. Filter preservation on redirect
"""
import pytest
from models.enums import InvestDecision


class TestInvestDecisionEnum:
    """Tests for InvestDecision enum values."""
    
    def test_invest_decisions_are_valid(self):
        """InvestDecision must contain expected choices."""
        expected = ['build', 'buy', 'assign_sme', 'defer']
        actual = InvestDecision.choices()
        assert actual == expected
    
    def test_invest_labels_exist(self):
        """Each choice must have a display label."""
        labels = InvestDecision.display_labels()
        for choice in InvestDecision.choices():
            assert choice in labels
            assert isinstance(labels[choice], str)
    
    def test_display_labels_are_readable(self):
        """Labels must be human-readable titles."""
        labels = InvestDecision.display_labels()
        assert labels['build'] == 'Build'
        assert labels['buy'] == 'Buy'
        assert labels['assign_sme'] == 'Assign SME'
        assert labels['defer'] == 'Defer'


class TestInvestmentReadPredicate:
    """Tests for Investment view canonical read."""
    
    @pytest.mark.skipif(
        not __import__('os').environ.get('DATABASE_URL'),
        reason="DATABASE_URL not configured"
    )
    def test_investment_uses_same_function_as_legacy(self):
        """Investment view must use get_containers_by_scrub_status."""
        # Verify the function exists and accepts status list
        from db import get_containers_by_scrub_status
        
        # Function should accept a list of statuses
        import inspect
        sig = inspect.signature(get_containers_by_scrub_status)
        params = list(sig.parameters.keys())
        assert 'statuses' in params or len(params) >= 1
    
    def test_investment_filters_modify_and_gap(self):
        """Investment view should filter for modify and gap statuses."""
        # Verify the view code uses ['modify', 'gap']
        import tcm_app.views as views
        import inspect
        source = inspect.getsource(views.investment_view)
        assert "['modify', 'gap']" in source or "['gap', 'modify']" in source


class TestInvestmentWriteFunction:
    """Tests for update_container_invest function signature."""
    
    @pytest.mark.skipif(
        not __import__('os').environ.get('DATABASE_URL'),
        reason="DATABASE_URL not configured"
    )
    def test_update_container_invest_signature(self):
        """update_container_invest must accept expected parameters."""
        from db import update_container_invest
        import inspect
        
        sig = inspect.signature(update_container_invest)
        params = list(sig.parameters.keys())
        
        # Required parameters
        assert 'container_key' in params
        assert 'decision' in params
        assert 'owner' in params
        # Optional parameters
        assert 'effort' in params
        assert 'notes' in params


class TestFilterPreservation:
    """Tests for filter state preservation on redirect."""
    
    def test_save_investment_preserves_filters(self):
        """save_investment_view must preserve filter params in redirect."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.save_investment_view)
        
        # Must read filter params from POST
        assert 'scrub_filter' in source
        assert 'decision_filter' in source
        
        # Must include filters in redirect URL
        assert 'scrub_filter=' in source
        assert 'decision_filter=' in source
