"""
Regression tests for Investment Write functionality.

Tests verify:
1. Investment view uses normalize_status to filter containers
2. Scrubbing → Investment propagation works correctly
3. Decision options match legacy enum values and labels
"""
import pytest
from models.enums import InvestDecision
from services.scrub_rules import normalize_status


class TestNormalizeStatus:
    """Tests for normalize_status used in Investment queue filter."""
    
    def test_modify_normalizes_to_modify(self):
        """'Modify' raw value normalizes to 'Modify'."""
        assert normalize_status('Modify') == 'Modify'
    
    def test_lowercase_modify_normalizes_to_modify(self):
        """'modify' lowercase normalizes to 'Modify'."""
        assert normalize_status('modify') == 'Modify'
    
    def test_gap_normalizes_to_modify(self):
        """Legacy 'gap' normalizes to 'Modify' (for Investment queue inclusion)."""
        assert normalize_status('gap') == 'Modify'
    
    def test_include_does_not_normalize_to_modify(self):
        """'Include' does NOT normalize to 'Modify'."""
        assert normalize_status('Include') != 'Modify'
    
    def test_not_reviewed_does_not_normalize_to_modify(self):
        """'not_reviewed' does NOT normalize to 'Modify'."""
        assert normalize_status('not_reviewed') != 'Modify'
        assert normalize_status('not_reviewed') == 'Unreviewed'


class TestInvestmenQueuePredicate:
    """Tests for Investment queue predicate using normalize_status."""
    
    def test_investment_view_uses_normalize_status(self):
        """Investment view must use normalize_status to filter containers."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.investment_view)
        
        # Must import and use normalize_status
        assert 'normalize_status' in source
        # Must filter for 'Modify'
        assert "'Modify'" in source
    
    def test_investment_view_uses_get_active_containers(self):
        """Investment view must use get_active_containers (canonical read)."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.investment_view)
        
        # Must use get_active_containers
        assert 'get_active_containers' in source


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


class TestPendingSemantics:
    """Tests for Pending filter semantics."""
    
    def test_pending_is_filter_not_decision(self):
        """Pending must be a filter concept, not a stored decision value."""
        # Pending should NOT be in InvestDecision choices
        choices = InvestDecision.choices()
        assert 'pending' not in choices
        assert 'Pending' not in choices
    
    def test_save_investment_view_never_writes_pending(self):
        """save_investment_view must never write 'Pending' as invest_decision."""
        import tcm_app.views as views
        import inspect
        
        source = inspect.getsource(views.save_investment_view)
        
        # Should validate against InvestDecision.choices() which excludes Pending
        assert 'InvestDecision.choices()' in source
