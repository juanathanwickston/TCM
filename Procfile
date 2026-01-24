# Django frontend (Demo_Only branch)
# Superuser must be created manually via one-off command, not automated
web: python manage.py migrate --noinput && gunicorn tcm_django.wsgi:application --bind 0.0.0.0:$PORT
