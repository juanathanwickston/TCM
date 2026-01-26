"""
Pytest configuration for Django tests.
"""
import os
import sys

# Add project root to path so tcm_django can be imported
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def pytest_configure():
    """Configure Django settings for pytest."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tcm_django.settings')
    
    import django
    django.setup()
