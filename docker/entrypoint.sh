#!/usr/bin/env bash
set -euo pipefail

echo "→ Migrazioni"
uv run python manage.py migrate --noinput

echo "→ File statici"
uv run python manage.py collectstatic --noinput

echo "→ Avvio gunicorn"
exec uv run gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile -
