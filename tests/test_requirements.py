"""
Dependency Guardrails

Prevents Streamlit packages from being added to production requirements.
Run with: pytest tests/test_requirements.py
"""

import os

FORBIDDEN_PACKAGES = [
    'streamlit',
    'streamlit-authenticator',
    'extra-streamlit-components',
]


def test_no_streamlit_in_production_requirements():
    """
    GUARDRAIL: requirements.txt must NOT contain Streamlit packages.
    
    Production uses requirements.txt. If you need Streamlit for local dev,
    add it to requirements-dev.txt instead.
    """
    requirements_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'requirements.txt'
    )
    
    with open(requirements_path, 'r') as f:
        lines = f.readlines()
    
    # Parse package lines (ignore comments and blank lines)
    packages = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            # Extract package name (before ==, >=, etc.)
            package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('<')[0].split('>')[0].strip().lower()
            packages.append(package_name)
    
    violations = []
    for forbidden in FORBIDDEN_PACKAGES:
        if forbidden.lower() in packages:
            violations.append(forbidden)
    
    assert not violations, (
        f"FORBIDDEN: Production requirements.txt contains Streamlit packages: {violations}. "
        f"Use requirements-dev.txt for local development instead."
    )


def test_requirements_prod_matches_requirements():
    """
    GUARDRAIL: requirements-prod.txt must be identical to requirements.txt.
    
    This ensures Railway build command and Railpack install phase
    use the same dependencies.
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    
    with open(os.path.join(base_dir, 'requirements.txt'), 'r') as f:
        req_txt = f.read()
    
    with open(os.path.join(base_dir, 'requirements-prod.txt'), 'r') as f:
        req_prod = f.read()
    
    assert req_txt == req_prod, (
        "requirements.txt and requirements-prod.txt must be identical. "
        "If you update one, update both."
    )
