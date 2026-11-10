"""Backend di override produzione (Mailpit) — apps/core/email/override.py."""

from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage

from apps.core.email.override import MailpitOverridableBackend
from apps.core.models import ImpostazioniPiattaforma

pytestmark = pytest.mark.django_db

LOCMEM = {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


@pytest.fixture
def mailers_prod(settings):
    # Stessi alias di config/settings/prod.py, con locmem al posto dei trasporti
    # reali: il messaggio registra in sent_using l'alias che l'ha inviato.
    settings.MAILERS = {
        "default": {"BACKEND": "apps.core.email.override.MailpitOverridableBackend"},
        "provider": LOCMEM,
        "mailpit": LOCMEM,
    }


def _messaggio() -> EmailMessage:
    return EmailMessage("Oggetto", "Corpo.", "a@example.com", ["dest@example.com"])


def test_nessun_messaggio_non_apre_connessione():
    backend = MailpitOverridableBackend()
    with patch("apps.core.email.override.mail.mailers") as mock_mailers:
        inviate = backend.send_messages([])

    assert inviate == 0
    mock_mailers.__getitem__.assert_not_called()


def test_flag_disattivo_usa_il_provider_configurato(mailers_prod):
    ImpostazioniPiattaforma.objects.update_or_create(pk=1, defaults={"email_su_mailpit": False})

    inviate = _messaggio().send()

    assert inviate == 1
    assert [m.sent_using for m in mail.outbox] == ["provider"]


def test_flag_attivo_usa_mailpit(settings, mailers_prod):
    settings.EMAIL_MAILPIT_HOST = "localhost"
    ImpostazioniPiattaforma.objects.update_or_create(pk=1, defaults={"email_su_mailpit": True})

    inviate = _messaggio().send()

    assert inviate == 1
    assert [m.sent_using for m in mail.outbox] == ["mailpit"]


def test_flag_attivo_senza_host_configurato_solleva_errore(settings, mailers_prod):
    settings.EMAIL_MAILPIT_HOST = ""
    ImpostazioniPiattaforma.objects.update_or_create(pk=1, defaults={"email_su_mailpit": True})
    backend = MailpitOverridableBackend()

    with pytest.raises(ImproperlyConfigured):
        backend.send_messages([_messaggio()])
    assert mail.outbox == []


def test_fail_silently_si_applica_all_errore_del_mailer_delegato(mailers_prod):
    connessione_rotta = MagicMock()
    connessione_rotta.send_messages.side_effect = OSError("connessione rifiutata")
    with patch("apps.core.email.override.mail.mailers") as mock_mailers:
        mock_mailers.__getitem__.return_value = connessione_rotta
        assert MailpitOverridableBackend(fail_silently=True).send_messages([_messaggio()]) == 0
        with pytest.raises(OSError):
            MailpitOverridableBackend().send_messages([_messaggio()])
