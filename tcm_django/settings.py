"""
Django settings for Training Catalogue Manager (TCM).

Demo_Only Branch - Django frontend replacing Streamlit.
Connects to existing PostgreSQL database via DATABASE_URL.

SECURITY:
- SECRET_KEY is REQUIRED in production (no fallback)
- DEBUG defaults to False
- ALLOWED_HOSTS must be explicitly set in production
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Load .env for local development
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# =============================================================================
# SECURITY SETTINGS - FAIL-CLOSED IN PRODUCTION
# =============================================================================

# Detect environment
_is_production = os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('PRODUCTION')

if _is_production:
    # PRODUCTION: Fail if SECRET_KEY not set
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is required in production")
    # DEBUG is always False in production - no override allowed
    DEBUG = False
    # ALLOWED_HOSTS must be explicitly set
    _hosts = os.environ.get('ALLOWED_HOSTS', '')
    if not _hosts:
        raise RuntimeError("ALLOWED_HOSTS environment variable is required in production")
    ALLOWED_HOSTS = [h.strip() for h in _hosts.split(',') if h.strip()]
    # CSRF trusted origins - explicit env var required (scheme + domain)
    # Set to: https://tcm-demoonly.up.railway.app
    _csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
    if not _csrf_origins:
        raise RuntimeError("CSRF_TRUSTED_ORIGINS environment variable is required in production (e.g., https://your-app.railway.app)")
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]
else:
    # LOCAL DEVELOPMENT: Permissive defaults
    SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-only-local-testing')
    DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')
    ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'whitenoise.runserver_nostatic',
    # TCM app (Django views)
    'tcm_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tcm_django.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'tcm_app' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'tcm_django.wsgi.application'


# =============================================================================
# DATABASE
# Uses existing PostgreSQL via DATABASE_URL environment variable.
# Django handles ONLY its own tables (auth_*, django_*).
# Business data uses existing db.py helpers.
# =============================================================================

DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3',
        conn_max_age=600,
        conn_health_checks=True,
    )
}


# =============================================================================
# PASSWORD VALIDATION
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =============================================================================
# SESSIONS (7-day lifetime per approval)
# =============================================================================

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days in seconds
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = _is_production  # Secure in production (HTTPS)


# =============================================================================
# ADDITIONAL SECURITY FOR PRODUCTION
# =============================================================================

if _is_production:
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'


# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'tcm_app' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
}


# =============================================================================
# AUTH REDIRECTS
# =============================================================================

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# =============================================================================
# DEFAULT PRIMARY KEY FIELD TYPE
# =============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# LOGGING - Output errors to stdout for Railway
# =============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
