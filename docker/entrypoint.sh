#!/bin/sh
set -e

echo "=== Starting Dormitory Management System Container ==="

# Wait for PostgreSQL database if configured
if [ -n "$DB_HOST" ]; then
    echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}..."
    while ! nc -z "$DB_HOST" "${DB_PORT:-5432}"; do
        sleep 0.5
    done
    echo "Database is ready!"
fi

# Run database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files for Nginx / WhiteNoise
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Ensure all residents have linked user accounts
echo "Synchronizing resident accounts..."
python manage.py setup_resident_accounts

echo "Starting Gunicorn WSGI Server on port 8000..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
