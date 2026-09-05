"""Backend Gmail (service account + OAuth) — apps/core/email/gmail.py."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage

from apps.core.email.gmail import GmailOAuthBackend, GmailServiceAccountBackend

SERVICE_ACCOUNT_JSON = json.dumps(
    {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "abc",
        "private_key": "-----BEGIN PRIVATE KEY-----\nfinta\n-----END PRIVATE KEY-----\n",
        "client_email": "invio@test-project.iam.gserviceaccount.com",
        "client_id": "123",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
)


def _messaggio() -> EmailMessage:
    return EmailMessage("Oggetto", "Corpo.", "mittente@example.com", ["dest@example.com"])


# ─── GmailServiceAccountBackend ──────────────────────────────────────────────


def test_service_account_richiede_json_o_file(settings):
    settings.GMAIL_SERVICE_ACCOUNT_JSON = ""
    settings.GMAIL_SERVICE_ACCOUNT_FILE = ""
    settings.GMAIL_MITTENTE = "segreteria@example.com"
    backend = GmailServiceAccountBackend()

    with pytest.raises(ImproperlyConfigured):
        backend.send_messages([_messaggio()])


def test_service_account_richiede_mittente(settings):
    settings.GMAIL_SERVICE_ACCOUNT_JSON = SERVICE_ACCOUNT_JSON
    settings.GMAIL_MITTENTE = ""
    backend = GmailServiceAccountBackend()

    with pytest.raises(ImproperlyConfigured):
        backend.send_messages([_messaggio()])


def test_service_account_json_malformato(settings):
    settings.GMAIL_SERVICE_ACCOUNT_JSON = "{non valido"
    settings.GMAIL_MITTENTE = "segreteria@example.com"
    backend = GmailServiceAccountBackend()

    with pytest.raises(ImproperlyConfigured):
        backend.send_messages([_messaggio()])


def test_service_account_invio_riuscito(settings):
    settings.GMAIL_SERVICE_ACCOUNT_JSON = SERVICE_ACCOUNT_JSON
    settings.GMAIL_MITTENTE = "segreteria@example.com"
    settings.EMAIL_TIMEOUT = 20
    backend = GmailServiceAccountBackend()

    credenziali_finte = MagicMock()
    credenziali_finte.token = "token-finto"
    credenziali_finte.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    risposta_finta = MagicMock()
    risposta_finta.raise_for_status.return_value = None

    with (
        patch(
            "apps.core.email.gmail.service_account.Credentials.from_service_account_info",
            return_value=credenziali_finte,
        ) as mock_from_info,
        patch("apps.core.email.gmail.GoogleAuthRequest"),
        patch("apps.core.email.gmail.requests.post", return_value=risposta_finta) as mock_post,
    ):
        inviate = backend.send_messages([_messaggio()])

    assert inviate == 1
    credenziali_finte.refresh.assert_called_once()
    mock_from_info.assert_called_once()
    _, kwargs = mock_from_info.call_args
    assert kwargs["subject"] == "segreteria@example.com"

    mock_post.assert_called_once()
    _, post_kwargs = mock_post.call_args
    assert post_kwargs["headers"]["Authorization"] == "Bearer token-finto"
    assert "raw" in post_kwargs["json"]


def test_service_account_usa_file_se_json_assente(settings, tmp_path):
    percorso = tmp_path / "service-account.json"
    percorso.write_text(SERVICE_ACCOUNT_JSON, encoding="utf-8")
    settings.GMAIL_SERVICE_ACCOUNT_JSON = ""
    settings.GMAIL_SERVICE_ACCOUNT_FILE = str(percorso)
    settings.GMAIL_MITTENTE = "segreteria@example.com"
    backend = GmailServiceAccountBackend()

    credenziali_finte = MagicMock()
    credenziali_finte.token = "token-finto"
    credenziali_finte.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
    risposta_finta = MagicMock()
    risposta_finta.raise_for_status.return_value = None

    with (
        patch(
            "apps.core.email.gmail.service_account.Credentials.from_service_account_info",
            return_value=credenziali_finte,
        ),
        patch("apps.core.email.gmail.GoogleAuthRequest"),
        patch("apps.core.email.gmail.requests.post", return_value=risposta_finta),
    ):
        inviate = backend.send_messages([_messaggio()])

    assert inviate == 1


def test_service_account_errore_api_non_logga_token(settings, caplog):
    settings.GMAIL_SERVICE_ACCOUNT_JSON = SERVICE_ACCOUNT_JSON
    settings.GMAIL_MITTENTE = "segreteria@example.com"
    backend = GmailServiceAccountBackend()

    credenziali_finte = MagicMock()
    credenziali_finte.token = "token-super-segreto"
    credenziali_finte.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    with (
        patch(
            "apps.core.email.gmail.service_account.Credentials.from_service_account_info",
            return_value=credenziali_finte,
        ),
        patch("apps.core.email.gmail.GoogleAuthRequest"),
        patch("apps.core.email.gmail.requests.post", side_effect=Exception("errore rete")),
        pytest.raises(Exception, match="errore rete"),
    ):
        backend.send_messages([_messaggio()])

    assert "token-super-segreto" not in caplog.text


# ─── GmailOAuthBackend ────────────────────────────────────────────────────────


def test_oauth_richiede_tutte_le_variabili(settings):
    settings.GMAIL_CLIENT_ID = ""
    settings.GMAIL_CLIENT_SECRET = "secret"
    settings.GMAIL_REFRESH_TOKEN = "refresh"
    backend = GmailOAuthBackend()

    with pytest.raises(ImproperlyConfigured):
        backend.send_messages([_messaggio()])


def test_oauth_invio_riuscito(settings):
    settings.GMAIL_CLIENT_ID = "client-id"
    settings.GMAIL_CLIENT_SECRET = "client-secret"
    settings.GMAIL_REFRESH_TOKEN = "refresh-token"
    settings.EMAIL_TIMEOUT = 20
    backend = GmailOAuthBackend()

    risposta_token = MagicMock()
    risposta_token.raise_for_status.return_value = None
    risposta_token.json.return_value = {"access_token": "token-oauth", "expires_in": 3599}

    risposta_invio = MagicMock()
    risposta_invio.raise_for_status.return_value = None

    with patch(
        "apps.core.email.gmail.requests.post", side_effect=[risposta_token, risposta_invio]
    ) as mock_post:
        inviate = backend.send_messages([_messaggio()])

    assert inviate == 1
    primo_url = mock_post.call_args_list[0].args[0]
    assert primo_url == "https://oauth2.googleapis.com/token"
    secondo_kwargs = mock_post.call_args_list[1].kwargs
    assert secondo_kwargs["headers"]["Authorization"] == "Bearer token-oauth"
