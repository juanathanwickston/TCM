"""
Template Regression Tests - Ensure all pages render without errors.

This test module catches template compilation errors BEFORE deploy.
If any template has syntax issues (like missing spaces in {% if %}),
these tests will fail.
"""
import pytest
from django.test import Client
from django.contrib.auth.models import User


@pytest.fixture
def authenticated_client(db):
    """Create an authenticated test client."""
    user = User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com'
    )
    client = Client()
    client.login(username='testuser', password='testpass123')
    return client


@pytest.mark.django_db
class TestTemplateRendering:
    """
    Template smoke tests - ensure all pages render HTTP 200.
    These catch TemplateSyntaxError at compile time.
    """
    
    def test_inventory_page_renders(self, authenticated_client):
        """
        GET /inventory/ must return 200.
        
        This test catches template syntax errors like:
        - {% if foo==bar %} (missing spaces around ==)
        - Invalid filter usage
        - Unclosed blocks
        """
        response = authenticated_client.get('/inventory/')
        assert response.status_code == 200, \
            f"Inventory page failed with status {response.status_code}"
    
    def test_dashboard_page_renders(self, authenticated_client):
        """GET /dashboard/ must return 200."""
        response = authenticated_client.get('/dashboard/')
        assert response.status_code == 200, \
            f"Dashboard page failed with status {response.status_code}"
    
    def test_scrubbing_page_renders(self, authenticated_client):
        """GET /scrubbing/ must return 200."""
        response = authenticated_client.get('/scrubbing/')
        assert response.status_code == 200, \
            f"Scrubbing page failed with status {response.status_code}"
    
    def test_investment_page_renders(self, authenticated_client):
        """GET /investment/ must return 200."""
        response = authenticated_client.get('/investment/')
        assert response.status_code == 200, \
            f"Investment page failed with status {response.status_code}"
    
    def test_login_page_renders(self):
        """GET /login/ must return 200 (unauthenticated)."""
        client = Client()
        response = client.get('/login/')
        assert response.status_code == 200, \
            f"Login page failed with status {response.status_code}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
