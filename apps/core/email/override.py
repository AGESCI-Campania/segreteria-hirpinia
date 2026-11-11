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

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from django.core.mail import EmailMessage

#: Alias di `MAILERS` definiti da `config/settings/prod.py` accanto a
#: "default" (che è questo backend): solo questo modulo li usa.
ALIAS_PROVIDER = "provider"
ALIAS_MAILPIT = "mailpit"

#: Contrassegno messo da `apps.core.invio_email.invia_email_template()` sui
#: messaggi che devono andare **sempre** su Mailpit, qualunque sia
#: l'interruttore globale: le email delle assemblee di prova «solo Mailpit»
#: (docs/plan_preparazione_assemblea.md, D26-D27). Chi lo mette non sa quale
#: provider è attivo: la scelta del trasporto resta solo qui.
HEADER_SOLO_MAILPIT = "X-Catello-Solo-Mailpit"


class MailpitOverridableBackend(BaseEmailBackend):
    """Delega al mailer "mailpit" se `ImpostazioniPiattaforma.corrente().email_su_mailpit`
    è vero, altrimenti al mailer "provider" (quello di `EMAIL_PROVIDER`)."""

    def __init__(self, fail_silently: bool = False, **kwargs: Any) -> None:
        # fail_silently arriva solo dai chiamanti che usano ancora l'argomento
        # deprecato in Django 6.1 (send(fail_silently=...)): con MAILERS non si
        # può più inoltrare al mailer delegato, quindi si applica qui.
        super().__init__(**kwargs)
        self.fail_silently = fail_silently

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0
        solo_mailpit = [m for m in email_messages if m.extra_headers.get(HEADER_SOLO_MAILPIT)]
        altri = [m for m in email_messages if not m.extra_headers.get(HEADER_SOLO_MAILPIT)]
        inviati = 0
        if solo_mailpit:
            # Mai un invio reale creduto deviato (D27): senza Mailpit si fallisce,
            # anche con fail_silently.
            self._verifica_mailpit()
            inviati += self._invia(ALIAS_MAILPIT, solo_mailpit)
        if altri:
            inviati += self._invia(self._alias_attivo(), altri)
        return inviati

    def _invia(self, alias: str, messaggi: Sequence[EmailMessage]) -> int:
        try:
            return mail.mailers[alias].send_messages(messaggi) or 0
        except Exception:
            if not self.fail_silently:
                raise
            return 0

    @staticmethod
    def _verifica_mailpit() -> None:
        if not settings.EMAIL_MAILPIT_HOST:
            raise ImproperlyConfigured(
                "Email da inviare solo su Mailpit, ma EMAIL_MAILPIT_HOST non è configurato."
            )

    def _alias_attivo(self) -> str:
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
            return ALIAS_MAILPIT
        return ALIAS_PROVIDER
