"""Interruttore di produzione per reindirizzare le email su Mailpit.

Deviazione dichiarata dalla regola "il provider si sceglie solo con
EMAIL_PROVIDER" (CLAUDE.md, § Email): qui la scelta del trasporto dipende
anche da un campo di `ImpostazioniPiattaforma`, letto a ogni invio, non da
una variabile d'ambiente letta una volta all'avvio. È un'eccezione
volutamente confinata a questo unico modulo — nessun'altra parte
dell'applicazione (view, service layer, allauth) verifica mai il provider
attivo o questo flag: si limitano, come sempre, a `django.core.mail`.

Usato solo da `config/settings/prod.py`, mai in sviluppo/test: lì il modo
per usare Mailpit resta `EMAIL_PROVIDER=smtp` puntato su
`localhost:1025` (vedi `docs/email/sviluppo-e-test.md`), senza passare da
qui.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

from . import backend_path

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from django.core.mail import EmailMessage
    from django.core.mail.backends.base import BaseEmailBackend as Connection


class MailpitOverridableBackend(BaseEmailBackend):
    """Delega a Mailpit se `ImpostazioniPiattaforma.corrente().email_su_mailpit`
    è vero, altrimenti al provider configurato in `EMAIL_PROVIDER`."""

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0
        return self._connessione_attiva().send_messages(email_messages) or 0

    def _connessione_attiva(self) -> Connection:
        from apps.core.models import ImpostazioniPiattaforma

        if ImpostazioniPiattaforma.corrente().email_su_mailpit:
            if not settings.EMAIL_MAILPIT_HOST:
                # Non dovrebbe accadere: ImpostazioniPiattaformaForm rifiuta di
                # attivare il flag senza EMAIL_MAILPIT_HOST configurato. Se
                # capita comunque (es. host rimosso da .env dopo l'attivazione),
                # fallire in modo esplicito è meglio che inviare email reali
                # credendo di averle deviate su un sink di test.
                raise ImproperlyConfigured(
                    "Impostazioni piattaforma ha email_su_mailpit=True ma "
                    "EMAIL_MAILPIT_HOST non è configurato."
                )
            return get_connection(
                backend="django.core.mail.backends.smtp.EmailBackend",
                host=settings.EMAIL_MAILPIT_HOST,
                port=settings.EMAIL_MAILPIT_PORT,
                use_tls=False,
                use_ssl=False,
                fail_silently=self.fail_silently,
            )
        return get_connection(
            backend=backend_path(settings.EMAIL_PROVIDER), fail_silently=self.fail_silently
        )
