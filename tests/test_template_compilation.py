"""
Template Compilation Tests
==========================
Catches template syntax errors BEFORE deployment.

Failures here mean the template cannot render and will 500 in production.
Run with: pytest tests/test_template_compilation.py -v
"""
from django.template.loader import get_template


class TestTemplateCompilation:
    """
    Compile every critical template. Syntax errors = immediate test failure.
    
    This catches:
    - Missing spaces around == in {% if %}
    - Unclosed {% for %} or {% if %} blocks
    - Invalid filter syntax
    - Missing {% load %} statements
    """
    
    def test_inventory_template_compiles(self):
        """Inventory template MUST compile without TemplateSyntaxError."""
        template = get_template('tcm_app/inventory.html')
        assert template is not None
        # PROOF TEST B: This will fail CI intentionally
        assert False, "INTENTIONAL FAILURE FOR PROOF TEST B"
    
    def test_dashboard_template_compiles(self):
        """Dashboard template MUST compile."""
        template = get_template('tcm_app/dashboard.html')
        assert template is not None
    
    def test_scrubbing_template_compiles(self):
        """Scrubbing template MUST compile."""
        template = get_template('tcm_app/scrubbing.html')
        assert template is not None
    
    def test_investment_template_compiles(self):
        """Investment template MUST compile."""
        template = get_template('tcm_app/investment.html')
        assert template is not None
    
    def test_tools_template_compiles(self):
        """Tools template MUST compile."""
        template = get_template('tcm_app/tools.html')
        assert template is not None
    
    def test_login_template_compiles(self):
        """Login template MUST compile."""
        template = get_template('tcm_app/login.html')
        assert template is not None
    
    def test_base_template_compiles(self):
        """Base template MUST compile."""
        template = get_template('tcm_app/base.html')
        assert template is not None
