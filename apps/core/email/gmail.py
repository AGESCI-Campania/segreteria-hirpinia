"""Backend email per Gmail/Google Workspace, via Gmail API.

Due varianti, entrambe sottoclassi di `apps.core.email.base.ApiEmailBackend`
(che gestisce già cache del token e conversione MIME):

- `GmailServiceAccountBackend` — service account con delega a livello di
  dominio (vedi docs/email/gmail-service-account.md), consigliata per
  Workspace: nessun token utente da rinnovare a mano.
- `GmailOAuthBackend` — refresh token OAuth (vedi docs/email/gmail-oauth.md),
  ripiego quando la delega di dominio non è disponibile.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from .base import ApiEmailBackend

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailServiceAccountBackend(ApiEmailBackend):
    """Delega a livello di dominio: il service account impersona
    `settings.GMAIL_MITTENTE` per lo scope `gmail.send`."""

    cache_key = "email:access_token:gmail_service_account"

    def _richiedi_token(self) -> tuple[str, int]:
        info = self._carica_service_account_info()
        if not settings.GMAIL_MITTENTE:
            raise ImproperlyConfigured("GMAIL_MITTENTE non configurato (gmail_service_account).")

        credenziali = service_account.Credentials.from_service_account_info(
            info, scopes=[GMAIL_SEND_SCOPE], subject=settings.GMAIL_MITTENTE
        )
        credenziali.refresh(GoogleAuthRequest())

        if not credenziali.token or not credenziali.expiry:
            raise ImproperlyConfigured("Impossibile ottenere un token di accesso Gmail.")

        # google-auth restituisce expiry come datetime naive in UTC.
        ora_utc = datetime.now(UTC).replace(tzinfo=None)
        durata = int((credenziali.expiry - ora_utc).total_seconds())
        return credenziali.token, max(durata, 60)

    @staticmethod
    def _carica_service_account_info() -> dict:
        if settings.GMAIL_SERVICE_ACCOUNT_JSON:
            try:
                return json.loads(settings.GMAIL_SERVICE_ACCOUNT_JSON)
            except json.JSONDecodeError as exc:
                raise ImproperlyConfigured(
                    "GMAIL_SERVICE_ACCOUNT_JSON non è un JSON valido."
                ) from exc
        if settings.GMAIL_SERVICE_ACCOUNT_FILE:
            with open(settings.GMAIL_SERVICE_ACCOUNT_FILE, encoding="utf-8") as file:
                return json.load(file)
        raise ImproperlyConfigured(
            "Serve GMAIL_SERVICE_ACCOUNT_JSON o GMAIL_SERVICE_ACCOUNT_FILE (gmail_service_account)."
        )

    def _invia_mime(self, mime: bytes, token: str, mittente: str) -> None:
        _invia_via_gmail_api(mime, token)


class GmailOAuthBackend(ApiEmailBackend):
    """Ripiego con refresh token OAuth: vedi § 8.3 della progettazione per i
    vincoli (nessuna delega di dominio disponibile)."""

    cache_key = "email:access_token:gmail_oauth"

    def _richiedi_token(self) -> tuple[str, int]:
        mancanti = [
            nome
            for nome, valore in (
                ("GMAIL_CLIENT_ID", settings.GMAIL_CLIENT_ID),
                ("GMAIL_CLIENT_SECRET", settings.GMAIL_CLIENT_SECRET),
                ("GMAIL_REFRESH_TOKEN", settings.GMAIL_REFRESH_TOKEN),
            )
            if not valore
        ]
        if mancanti:
            raise ImproperlyConfigured(f"gmail_oauth: variabili mancanti: {', '.join(mancanti)}.")

        risposta = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "refresh_token": settings.GMAIL_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=settings.EMAIL_TIMEOUT,
        )
        risposta.raise_for_status()
        dati = risposta.json()
        return dati["access_token"], int(dati.get("expires_in", 3600))

    def _invia_mime(self, mime: bytes, token: str, mittente: str) -> None:
        _invia_via_gmail_api(mime, token)


def _invia_via_gmail_api(mime: bytes, token: str) -> None:
    raw = base64.urlsafe_b64encode(mime).decode("ascii")
    risposta = requests.post(
        GMAIL_SEND_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"raw": raw},
        timeout=settings.EMAIL_TIMEOUT,
    )
    risposta.raise_for_status()
