#!/usr/bin/env bash
# Run Dormitory Management server accessible from outside on port 8080
cd "$(dirname "$0")"
exec .venv/bin/python manage.py runserver 0.0.0.0:8080 "$@"
