#!/usr/bin/env python
"""
Create superuser from environment variables.
Used for Railway deployment where console access is limited.

Set these env vars:
- DJANGO_SUPERUSER_USERNAME
- DJANGO_SUPERUSER_EMAIL  
- DJANGO_SUPERUSER_PASSWORD

Then run: python create_superuser.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tcm_django.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if not username or not password:
    print("DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD are required")
    sys.exit(0)  # Exit cleanly so deploy doesn't fail

if User.objects.filter(username=username).exists():
    print(f"Superuser '{username}' already exists, skipping creation")
    sys.exit(0)

User.objects.create_superuser(username=username, email=email, password=password)
print(f"Superuser '{username}' created successfully")
