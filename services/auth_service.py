"""
Authentication service for Training Catalogue Manager.

Provides streamlit-authenticator integration with environment variable configuration.
Fails closed if required credentials are not available.
"""

import os
import streamlit_authenticator as stauth


def get_authenticator():
    """
    Create and configure the authenticator from environment variables.
    
    Required environment variables:
    - AUTH_USERNAMES: comma-separated list of usernames
    - AUTH_PASSWORDS: comma-separated list of hashed passwords
    - AUTH_NAMES: comma-separated list of display names
    - AUTH_COOKIE_KEY: unique key for cookie encryption (32+ chars)
    
    Raises:
        RuntimeError: If any required variable is missing or invalid
    """
    # Load from environment
    usernames_str = os.environ.get("AUTH_USERNAMES", "")
    passwords_str = os.environ.get("AUTH_PASSWORDS", "")
    names_str = os.environ.get("AUTH_NAMES", "")
    cookie_key = os.environ.get("AUTH_COOKIE_KEY", "")
    
    # Fail closed if missing
    if not usernames_str:
        raise RuntimeError("AUTH_USERNAMES not set. Cannot proceed.")
    if not passwords_str:
        raise RuntimeError("AUTH_PASSWORDS not set. Cannot proceed.")
    if not names_str:
        raise RuntimeError("AUTH_NAMES not set. Cannot proceed.")
    if not cookie_key:
        raise RuntimeError("AUTH_COOKIE_KEY not set. Cannot proceed.")
    
    # Parse comma-separated values
    usernames = [u.strip() for u in usernames_str.split(",") if u.strip()]
    passwords = [p.strip() for p in passwords_str.split(",") if p.strip()]
    names = [n.strip() for n in names_str.split(",") if n.strip()]
    
    # Validate equal lengths
    if len(usernames) != len(passwords) or len(usernames) != len(names):
        raise RuntimeError(
            f"AUTH_USERNAMES ({len(usernames)}), AUTH_PASSWORDS ({len(passwords)}), "
            f"and AUTH_NAMES ({len(names)}) must have equal number of entries"
        )
    
    if len(usernames) == 0:
        raise RuntimeError("No users configured in AUTH_USERNAMES")
    
    # Validate cookie key length
    if len(cookie_key) < 32:
        raise RuntimeError("AUTH_COOKIE_KEY must be at least 32 characters")
    
    # Build credentials dict for streamlit-authenticator
    credentials = {
        "usernames": {
            username: {
                "email": f"{username}@internal",  # dummy email
                "name": name,
                "password": password
            }
            for username, name, password in zip(usernames, names, passwords)
        }
    }
    
    cookie_config = {
        "expiry_days": 7,
        "key": cookie_key,
        "name": "training_catalog_auth"
    }
    
    return stauth.Authenticate(
        credentials,
        cookie_config["name"],
        cookie_config["key"],
        cookie_config["expiry_days"]
    )


def hash_password(plaintext: str) -> str:
    """
    Hash a plaintext password for use in AUTH_PASSWORDS.
    
    Usage: 
        python -c "from services.auth_service import hash_password; print(hash_password('your_password'))"
    """
    return stauth.Hasher([plaintext]).generate()[0]


def get_credentials():
    """
    Load and return credentials dict from environment.
    Used for direct validation without the authenticator widget.
    
    Returns:
        Dict with structure: {username: {"name": display_name, "password": hashed_password}}
    """
    usernames_str = os.environ.get("AUTH_USERNAMES", "")
    passwords_str = os.environ.get("AUTH_PASSWORDS", "")
    names_str = os.environ.get("AUTH_NAMES", "")
    
    if not all([usernames_str, passwords_str, names_str]):
        return {}
    
    usernames = [u.strip() for u in usernames_str.split(",") if u.strip()]
    passwords = [p.strip() for p in passwords_str.split(",") if p.strip()]
    names = [n.strip() for n in names_str.split(",") if n.strip()]
    
    if len(usernames) != len(passwords) or len(usernames) != len(names):
        return {}
    
    return {
        username: {"name": name, "password": password}
        for username, name, password in zip(usernames, names, passwords)
    }


def validate_credentials(username: str, password: str) -> tuple:
    """
    Validate username/password against stored credentials.
    """
    import logging
    import bcrypt
    
    _log = logging.getLogger("auth")
    credentials = get_credentials()
    
    _log.info(f"validate_credentials: username='{username}', credentials_count={len(credentials)}")
    
    if not username or not password:
        _log.warning("Empty username or password")
        return (False, "")
    
    if not credentials:
        _log.warning("No credentials loaded")
        return (False, "")
    
    # Case-insensitive username lookup
    entered_username = username.strip().lower()
    user_data = None
    
    for stored_username, data in credentials.items():
        _log.info(f"Checking stored username: '{stored_username}'")
        if stored_username.lower() == entered_username:
            user_data = data
            _log.info(f"Found matching user: {stored_username}")
            break
    
    if not user_data:
        _log.warning(f"User '{username}' not found")
        return (False, "")
    
    stored_hash = user_data["password"]
    _log.info(f"Stored hash starts with: {stored_hash[:20]}...")
    
    # bcrypt comparison
    try:
        result = bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        _log.info(f"bcrypt.checkpw result: {result}")
        if result:
            return (True, user_data["name"])
    except Exception as e:
        _log.error(f"bcrypt check failed: {e}")
    
    return (False, "")
