# Auth & Permissions — Django Migration

**Purpose**: Define login behavior, session expectations, and Tools gating logic.

---

## Authentication Model

| Aspect | Specification |
|--------|---------------|
| Framework | Django built-in auth (`django.contrib.auth`) |
| SSO | ❌ Not used |
| Microsoft integration | ❌ Not used |
| Credentials | Username/email + password |
| Password storage | Django's default (PBKDF2 + SHA256) |

---

## Session Behavior

| Aspect | Specification |
|--------|---------------|
| Session backend | Database (`django.contrib.sessions.backends.db`) |
| Session table | `django_session` (Django-managed) |
| Session cookie name | `sessionid` (Django default) |
| Session lifetime | 7 days (reduced from default for security) |
| CSRF | Enabled (Django default) |

---

## Login Flow

```
Browser → GET /login/
       ← Login form (Bootstrap styled)
       
Browser → POST /login/ {username, password}
       ← If valid: Set session cookie, redirect to /dashboard/
       ← If invalid: Re-render form with error message

Browser → GET /dashboard/ (with session cookie)
       ← If authenticated: Render dashboard
       ← If not authenticated: Redirect to /login/
```

### Login Page Requirements
- Center-aligned card layout
- Username field
- Password field  
- Submit button
- Error message area (for invalid credentials)
- No "remember me" checkbox (sessions handle this)
- No password reset (out of scope)

---

## Logout Flow

```
Browser → POST /logout/
       ← Clear session, redirect to /login/
```

### Logout Requirements
- Available from sidebar/navbar
- POST request (CSRF protected)
- Clears session completely
- Redirects to login page

---

## Permission Model

### All Authenticated Users
| Page | Access |
|------|--------|
| Dashboard | ✅ Full access |
| Inventory | ✅ Full access (read + audience edits) |
| Scrubbing | ✅ Full access (read + writes) |
| Investment | ✅ Full access (read + writes) |
| Tools | ❌ Blocked |

### Superuser Only (John)
| Page | Access |
|------|--------|
| Tools | ✅ Full access |

---

## Tools Access Gate — Implementation

```python
# Django view decorator pattern
from django.http import HttpResponseForbidden

def tools_view(request):
    # SUPERUSER GATE
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied. Superuser required.")
    
    # ... render Tools page ...
```

### Alternative: Class-based view
```python
from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import TemplateView

class ToolsView(UserPassesTestMixin, TemplateView):
    template_name = 'tools.html'
    
    def test_func(self):
        return self.request.user.is_superuser
```

---

## Initial User Setup

### Creating John (superuser)

```bash
python manage.py createsuperuser
# Username: john
# Email: john@example.com
# Password: (secure password)
```

This is a one-time setup. John can create additional users via Django admin if needed.

---

## Environment Variables (Django)

| Variable | Purpose | Required |
|----------|---------|----------|
| `SECRET_KEY` | Django secret key | ✅ Yes |
| `DATABASE_URL` | PostgreSQL connection | ✅ Yes |
| `DEBUG` | Debug mode (False in prod) | ✅ Yes |
| `ALLOWED_HOSTS` | Allowed hostnames | ✅ Yes (prod) |

**Note**: The Streamlit `AUTH_*` environment variables are no longer used. Django manages its own auth.

---

## Migration from Streamlit Auth

| Streamlit | Django |
|-----------|--------|
| `AUTH_USERNAMES` | Django User model |
| `AUTH_PASSWORDS` (bcrypt) | Django User.password (PBKDF2) |
| `AUTH_NAMES` | Django User.first_name |
| `AUTH_COOKIE_KEY` | `SECRET_KEY` |
| streamlit-authenticator | `django.contrib.auth` |

### Data Migration Steps
1. Create Django superuser (John) manually
2. No password migration needed (Django uses different hash)
3. Old Streamlit env vars can be removed after Django is live

---

## Security Checklist

- [x] CSRF protection enabled
- [x] Session cookies HTTP-only
- [x] Secure cookies in production (HTTPS)
- [x] Password hashing (PBKDF2)
- [x] Login required for all pages
- [x] Superuser gate on Tools
- [x] No raw SQL injection (using parameterized queries via db.py)
