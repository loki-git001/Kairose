#!/bin/sh
set -e

echo "==> Waiting for PostgreSQL..."
while ! uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
" 2>/dev/null; do
  sleep 1
done

echo "==> Running migrations..."
uv run python manage.py migrate --noinput

echo "==> Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "==> Starting Gunicorn..."
exec uv run gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120 \
  --access-logfile -