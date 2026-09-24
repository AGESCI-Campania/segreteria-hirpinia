"""Client minimale per l'upload su Google Drive (D-59, F9): stesso pattern
REST leggero già in uso per il backend Gmail
(`apps.core.email.gmail.GmailServiceAccountBackend`) — niente SDK
`google-api-python-client`, solo `google-auth` (nuovo extra opzionale
`drive` in pyproject.toml, indipendente da `gmail`) + `requests`.

**Import lazy, sempre dentro le funzioni**, mai a livello di modulo (stesso
principio già applicato a WeasyPrint in `pdf.py`): `drive_replica.py` viene
importato incondizionatamente da `transizioni.py::liquida()`, quindi questo
modulo deve restare importabile anche in un deploy senza `--extra drive` —
altrimenti qualunque liquidazione romperebbe l'avvio dell'app per chi non
usa la replica.

Un service account non ha spazio proprio su Drive (V-8 dei requisiti): la
destinazione è sempre un **Drive condiviso** (`supportsAllDrives=true` su
ogni chiamata), mai il "My Drive" del service account."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


def replica_configurata() -> bool:
    """D-59: la replica è attiva solo se il Drive condiviso è configurato
    (V-8) — finché non lo è, `enqueue_copie_drive()`/`riconcilia_copie_drive()`
    restano no-op silenziosi, non un errore. Non importa `google.oauth2`: chi
    non configura la replica non deve installare l'extra `drive`."""
    return bool(settings.DRIVE_SHARED_DRIVE_ID and settings.DRIVE_FOLDER_ID)


def _carica_service_account_info() -> dict:
    if settings.DRIVE_SERVICE_ACCOUNT_JSON:
        try:
            return json.loads(settings.DRIVE_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as errore:
            raise ImproperlyConfigured(
                "DRIVE_SERVICE_ACCOUNT_JSON non è un JSON valido."
            ) from errore
    if settings.DRIVE_SERVICE_ACCOUNT_FILE:
        with open(settings.DRIVE_SERVICE_ACCOUNT_FILE) as file:
            return json.load(file)
    raise ImproperlyConfigured(
        "Serve DRIVE_SERVICE_ACCOUNT_JSON o DRIVE_SERVICE_ACCOUNT_FILE per la replica su Drive."
    )


def _token_accesso() -> str:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account

    info = _carica_service_account_info()
    credenziali = service_account.Credentials.from_service_account_info(info, scopes=[DRIVE_SCOPE])
    credenziali.refresh(GoogleAuthRequest())
    if not credenziali.token:
        raise ImproperlyConfigured("Impossibile ottenere un token di accesso Drive.")
    return credenziali.token


def carica_file(*, nome: str, contenuto: bytes, content_type: str) -> str:
    """Carica un file nella cartella configurata del Drive condiviso, upload
    multipart in un'unica richiesta — adeguato ai limiti già imposti sui
    giustificativi (A-11, 10 MB): un file più grande richiederebbe l'upload
    ripristinabile di Drive, non necessario qui.

    Restituisce l'id del file caricato. Solleva l'eccezione di `requests` in
    caso di errore di rete/HTTP: il chiamante (`drive_replica.py`) la
    traduce in uno stato di fallimento tracciato, mai propagata a una view."""
    import requests

    token = _token_accesso()
    metadata = {"name": nome, "parents": [settings.DRIVE_FOLDER_ID]}
    parti: dict[str, tuple[str | None, str | bytes, str]] = {
        "metadata": (None, json.dumps(metadata), "application/json"),
        "file": (nome, contenuto, content_type),
    }
    risposta = requests.post(
        DRIVE_UPLOAD_URL,
        params={"uploadType": "multipart", "supportsAllDrives": "true"},
        headers={"Authorization": f"Bearer {token}"},
        files=parti,
        timeout=30,
    )
    risposta.raise_for_status()
    dati: dict = risposta.json()
    return dati["id"]
