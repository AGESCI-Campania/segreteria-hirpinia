#!/usr/bin/env bash
set -euo pipefail

# Nota: la tabella della cache di produzione (settings.CACHES, backend "db") va
# creata una tantum con `manage.py createcachetable`, comando NON idempotente
# (fallisce se la tabella esiste già). Va eseguito manualmente al primo deploy,
# non qui: altrimenti romperebbe ogni riavvio successivo del container.
# Vedi README §Produzione.

# --no-sync: l'immagine ha già l'ambiente sincronizzato in fase di build
# (`uv sync --frozen --no-dev`). Senza questo flag, `uv run` risincronizza ad ogni
# avvio del container, scaricando anche le dipendenze di sviluppo escluse a build time.
echo "→ Migrazioni"
uv run --no-sync python manage.py migrate --noinput

echo "→ File statici"
uv run --no-sync python manage.py collectstatic --noinput

echo "→ Avvio gunicorn"
exec uv run --no-sync gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile -
