"""Backend di override produzione (Mailpit) — apps/core/email/override.py."""

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage

from apps.core.email.override import MailpitOverridableBackend
from apps.core.models import ImpostazioniPiattaforma

pytestmark = pytest.mark.django_db


def _messaggio() -> EmailMessage:
    return EmailMessage("Oggetto", "Corpo.", "a@example.com", ["dest@example.com"])


def test_nessun_messaggio_non_apre_connessione():
    backend = MailpitOverridableBackend()
    with patch("apps.core.email.override.get_connection") as mock_get_connection:
        inviate = backend.send_messages([])

    assert inviate == 0
    mock_get_connection.assert_not_called()


def test_flag_disattivo_usa_il_provider_configurato(settings):
    settings.EMAIL_PROVIDER = "console"
    ImpostazioniPiattaforma.objects.update_or_create(pk=1, defaults={"email_su_mailpit": False})
    backend = MailpitOverridableBackend()

    connessione_finta = MagicMock()
    connessione_finta.send_messages.return_value = 1
    with patch(
        "apps.core.email.override.get_connection", return_value=connessione_finta
    ) as mock_get_connection:
        inviate = backend.send_messages([_messaggio()])

    assert inviate == 1
    mock_get_connection.assert_called_once_with(
        backend="apps.core.email.console.ConsoleFileEmailBackend", fail_silently=False
    )


def test_flag_attivo_usa_mailpit(settings):
    settings.EMAIL_MAILPIT_HOST = "localhost"
    settings.EMAIL_MAILPIT_PORT = 1025
    ImpostazioniPiattaforma.objects.update_or_create(pk=1, defaults={"email_su_mailpit": True})
    backend = MailpitOverridableBackend()

    connessione_finta = MagicMock()
    connessione_finta.send_messages.return_value = 1
    with patch(
        "apps.core.email.override.get_connection", return_value=connessione_finta
    ) as mock_get_connection:
        inviate = backend.send_messages([_messaggio()])

    assert inviate == 1
    mock_get_connection.assert_called_once_with(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host="localhost",
        port=1025,
        use_tls=False,
        use_ssl=False,
        fail_silently=False,
    )


def test_flag_attivo_senza_host_configurato_solleva_errore(settings):
    settings.EMAIL_MAILPIT_HOST = ""
    ImpostazioniPiattaforma.objects.update_or_create(pk=1, defaults={"email_su_mailpit": True})
    backend = MailpitOverridableBackend()

    with pytest.raises(ImproperlyConfigured):
        backend.send_messages([_messaggio()])
