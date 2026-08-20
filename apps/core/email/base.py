"""Base condivisa per i backend che inviano via API HTTP invece che via SMTP.

Gmail e Microsoft Graph differiscono solo per come si ottiene il token e per l'endpoint
di invio: la conversione del messaggio Django in MIME, la gestione di ``fail_silently``
e la cache del token di accesso sono identiche e stanno qui.

Le sottoclassi implementano soltanto:
    - ``_access_token()``  -> str
    - ``_invia_mime(mime: bytes, token: str, mittente: str) -> None``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend

if TYPE_CHECKING:  # pragma: no cover
    from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

#: Margine di sicurezza sulla scadenza del token: i token di accesso durano un'ora,
#: li teniamo in cache un po' meno per non usarne uno scaduto a metà invio.
CACHE_TOKEN_SECONDI = 3000


class ApiEmailBackend(BaseEmailBackend):
    """Backend astratto per l'invio tramite API del provider."""

    #: Chiave di cache del token di accesso. Le sottoclassi la differenziano.
    cache_key = "email:access_token"

    # ── da implementare nelle sottoclassi ────────────────────────────────────

    def _richiedi_token(self) -> tuple[str, int]:
        """Ottiene un nuovo token di accesso. Restituisce (token, durata_secondi)."""
        raise NotImplementedError

    def _invia_mime(self, mime: bytes, token: str, mittente: str) -> None:
        """Invia un messaggio MIME già serializzato tramite l'API del provider."""
        raise NotImplementedError

    # ── implementazione condivisa ────────────────────────────────────────────

    def _access_token(self) -> str:
        token = cache.get(self.cache_key)
        if token:
            return token
        token, durata = self._richiedi_token()
        cache.set(self.cache_key, token, min(durata - 60, CACHE_TOKEN_SECONDI))
        return token

    def send_messages(self, email_messages: list[EmailMessage]) -> int:
        if not email_messages:
            return 0

        inviati = 0
        token = self._access_token()

        for message in email_messages:
            try:
                self._invia_mime(
                    mime=message.message().as_bytes(linesep="\r\n"),
                    token=token,
                    mittente=message.from_email,
                )
                inviati += 1
            except Exception:
                # Mai loggare il messaggio o il token: il primo contiene dati
                # personali, il secondo e' una credenziale.
                logger.exception(
                    "Invio email fallito (provider=%s, destinatari=%d)",
                    type(self).__name__,
                    len(message.recipients()),
                )
                if not self.fail_silently:
                    raise
        return inviati
