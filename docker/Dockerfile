FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# WeasyPrint richiede le librerie di rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Extra opzionale per il provider email scelto: "gmail", "microsoft" o vuoto
# (solo smtp/console/locmem, default). Mai obbligatorio: un deploy SMTP non
# deve installare google-auth/msal (vedi CLAUDE.md § Email).
ARG EMAIL_EXTRA=""
# Extra opzionale "drive" per la replica su Google Drive (D-59, F9): vuoto
# di default, chi non configura DRIVE_SHARED_DRIVE_ID/DRIVE_FOLDER_ID non
# deve installare google-auth. Indipendente da EMAIL_EXTRA: un deploy smtp
# con la replica attiva imposta solo DRIVE_EXTRA=drive.
ARG DRIVE_EXTRA=""

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
    ${EMAIL_EXTRA:+--extra "$EMAIL_EXTRA"} ${DRIVE_EXTRA:+--extra "$DRIVE_EXTRA"}

COPY . .
RUN uv sync --frozen --no-dev \
    ${EMAIL_EXTRA:+--extra "$EMAIL_EXTRA"} ${DRIVE_EXTRA:+--extra "$DRIVE_EXTRA"}

RUN chmod +x docker/entrypoint.sh
ENTRYPOINT ["docker/entrypoint.sh"]
