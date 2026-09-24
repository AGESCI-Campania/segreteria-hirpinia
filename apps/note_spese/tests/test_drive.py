"""Client Drive (D-59, F9): apps/note_spese/drive.py. Gli import di
`google.oauth2`/`requests` sono lazy (dentro le funzioni, non a livello di
modulo — vedi il docstring del modulo), quindi i patch bersagliano i moduli
sorgente reali (`google.oauth2.service_account`, `requests.post`), non
nomi importati in drive.py."""

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.note_spese.drive import _carica_service_account_info, carica_file, replica_configurata

SERVICE_ACCOUNT_JSON = (
    '{"type":"service_account","project_id":"test",'
    '"client_email":"drive@test.iam.gserviceaccount.com","client_id":"1"}'
)


class TestReplicaConfigurata:
    def test_falsa_se_mancano_entrambi_gli_id(self, settings):
        settings.DRIVE_SHARED_DRIVE_ID = ""
        settings.DRIVE_FOLDER_ID = ""
        assert replica_configurata() is False

    def test_falsa_se_manca_la_cartella(self, settings):
        settings.DRIVE_SHARED_DRIVE_ID = "drive-id"
        settings.DRIVE_FOLDER_ID = ""
        assert replica_configurata() is False

    def test_vera_se_configurati_entrambi(self, settings):
        settings.DRIVE_SHARED_DRIVE_ID = "drive-id"
        settings.DRIVE_FOLDER_ID = "folder-id"
        assert replica_configurata() is True


class TestCaricaServiceAccountInfo:
    def test_richiede_json_o_file(self, settings):
        settings.DRIVE_SERVICE_ACCOUNT_JSON = ""
        settings.DRIVE_SERVICE_ACCOUNT_FILE = ""
        with pytest.raises(ImproperlyConfigured):
            _carica_service_account_info()

    def test_json_malformato(self, settings):
        settings.DRIVE_SERVICE_ACCOUNT_JSON = "{non valido"
        with pytest.raises(ImproperlyConfigured):
            _carica_service_account_info()

    def test_json_valido(self, settings):
        settings.DRIVE_SERVICE_ACCOUNT_JSON = SERVICE_ACCOUNT_JSON
        info = _carica_service_account_info()
        assert info["client_email"] == "drive@test.iam.gserviceaccount.com"


class TestCaricaFile:
    def test_upload_riuscito_restituisce_id(self, settings):
        settings.DRIVE_SERVICE_ACCOUNT_JSON = SERVICE_ACCOUNT_JSON
        settings.DRIVE_FOLDER_ID = "folder-id"

        credenziali_finte = MagicMock()
        credenziali_finte.token = "token-finto"

        risposta_finta = MagicMock()
        risposta_finta.raise_for_status.return_value = None
        risposta_finta.json.return_value = {"id": "drive-file-id-123"}

        with (
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_info",
                return_value=credenziali_finte,
            ) as mock_from_info,
            patch("google.auth.transport.requests.Request"),
            patch("requests.post", return_value=risposta_finta) as mock_post,
        ):
            file_id = carica_file(
                nome="scontrino.jpg", contenuto=b"finto-jpeg", content_type="image/jpeg"
            )

        assert file_id == "drive-file-id-123"
        credenziali_finte.refresh.assert_called_once()
        mock_from_info.assert_called_once()
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["params"]["supportsAllDrives"] == "true"
        assert kwargs["headers"]["Authorization"] == "Bearer token-finto"

    def test_token_mancante_solleva_errore_configurazione(self, settings):
        settings.DRIVE_SERVICE_ACCOUNT_JSON = SERVICE_ACCOUNT_JSON
        settings.DRIVE_FOLDER_ID = "folder-id"

        credenziali_finte = MagicMock()
        credenziali_finte.token = None

        with (
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_info",
                return_value=credenziali_finte,
            ),
            patch("google.auth.transport.requests.Request"),
            pytest.raises(ImproperlyConfigured),
        ):
            carica_file(nome="x.pdf", contenuto=b"%PDF-1.4", content_type="application/pdf")
