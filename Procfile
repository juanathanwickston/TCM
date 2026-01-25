web: python manage.py migrate --no-input && python manage.py collectstatic --no-input && gunicorn tcm_django.wsgi:application --bind 0.0.0.0:$PORT --timeout 180
