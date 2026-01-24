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
    Hash a plaintext password using bcrypt.
    
    BCRYPT-ONLY. No streamlit-authenticator dependency.
    
    Usage (secure, no echo): 
        python -c "import bcrypt, getpass; pw=getpass.getpass('Password: ').encode(); print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())"
    
    Usage (direct):
        python -c "from services.auth_service import hash_password; print(hash_password('your_password'))"
    """
    import bcrypt
    return bcrypt.hashpw(plaintext.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


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
    
    BCRYPT ONLY. Fails closed if stored hash is not valid bcrypt format.
    
    Returns:
        Tuple of (success: bool, display_name: str)
    """
    import logging
    import bcrypt
    
    _log = logging.getLogger("auth")
    
    credentials = get_credentials()
    
    if not username or not password:
        return (False, "")
    
    if not credentials:
        _log.error("AUTH ERROR: No credentials loaded from environment")
        return (False, "")
    
    # Case-insensitive username lookup
    entered_username = username.strip().lower()
    user_data = None
    
    for stored_username, data in credentials.items():
        if stored_username.lower() == entered_username:
            user_data = data
            break
    
    if not user_data:
        return (False, "")
    
    stored_hash = user_data["password"]
    
    # FAIL-CLOSED: Validate bcrypt hash format before attempting verification
    # Valid bcrypt hashes start with $2a$, $2b$, or $2y$
    if not (stored_hash.startswith('$2a$') or 
            stored_hash.startswith('$2b$') or 
            stored_hash.startswith('$2y$')):
        _log.error(
            f"AUTH ERROR: Stored hash for user '{username}' is not valid bcrypt format. "
            f"Hash starts with: '{stored_hash[:10]}...'. "
            f"Regenerate hash using: python -c \"from services.auth_service import hash_password; print(hash_password('yourpassword'))\""
        )
        return (False, "")
    
    # Standard bcrypt hash length check (60 chars for most bcrypt implementations)
    if len(stored_hash) < 50:
        _log.error(
            f"AUTH ERROR: Stored hash for user '{username}' appears truncated. "
            f"Length: {len(stored_hash)}, expected ~60 chars."
        )
        return (False, "")
    
    # Bcrypt verification
    try:
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            _log.info(f"User '{username}' authenticated successfully")
            return (True, user_data["name"])
        else:
            return (False, "")
    except Exception as e:
        _log.error(f"AUTH ERROR: bcrypt verification failed for user '{username}': {e}")
        return (False, "")

