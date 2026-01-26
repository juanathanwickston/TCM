"""
Context Processors
==================
Add global template context variables.
"""
import os


def build_info(request):
    """
    Add build SHA to every template for deployed version visibility.
    
    Uses RAILWAY_GIT_COMMIT_SHA if available (set by Railway at deploy time).
    Shows 'unknown' if not running on Railway.
    """
    sha = os.environ.get('RAILWAY_GIT_COMMIT_SHA', 'unknown')
    # Show first 8 chars for readability
    return {
        'BUILD_SHA': sha[:8] if sha != 'unknown' else 'unknown'
    }
