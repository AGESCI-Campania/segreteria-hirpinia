"""Test delle viste di import PDF di autorizzazione: perimetro e flusso
anteprima→conferma (stesso principio di test_views_importazione.py)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo, ImportazioneAutorizzazioni
from apps.anagrafica.parser.autorizzazioni import ParseResult
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def account_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return _con_mfa_configurata(utente)


@pytest.fixture(autouse=True)
def _parse_pdf_stub(monkeypatch, capo, gruppo):
    """Le viste passano dai bytes caricati al parser reale: qui si sostituisce
    parse_pdf con uno stub, come nei test del service layer, perché la view è
    testata per il flusso di sessione/permessi, non per il parsing PDF vero
    (già coperto altrove)."""

    def _stub(source):
        return ParseResult(
            data_aggiornamento=datetime.datetime(2026, 1, 15),
            anno=ANNO,
            gruppo_nome=gruppo.nome,
            gruppo_codice=gruppo.codice,
            records=[
                {
                    "codice_socio": capo.codice_socio,
                    "nome": "MARIO ROSSI",
                    "gruppo": gruppo.nome,
                    "codice_gruppo": gruppo.codice,
                    "unita": "H1 BRANCO MISTO",
                    "branca": "L/C",
                    "genere_unita": "MISTO",
                    "genere": "M",
                    "livello_foca": 1,
                    "funzione": "CAPO UNITÀ",
                    "anno": ANNO,
                }
            ],
        )

    monkeypatch.setattr("apps.anagrafica.importazione_autorizzazioni.parse_pdf", _stub)


def _file_pdf(nome="e0133.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(nome, b"%PDF-fake", content_type="application/pdf")


class TestPerimetro:
    def test_cg_non_accede_allimport_pdf(self, client, account_gruppo):
        client.force_login(account_gruppo)
        response = client.get("/anagrafica/importazioni-autorizzazioni/")
        assert response.status_code == 403

    def test_segreteria_accede_allimport_pdf(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/importazioni-autorizzazioni/")
        assert response.status_code == 200

    def test_accesso_negato_anonimo(self, client):
        response = client.get("/anagrafica/importazioni-autorizzazioni/")
        assert response.status_code == 302


class TestFlussoAnteprimaConferma:
    def test_anteprima_non_scrive_nulla(self, client, segreteria, capo):
        client.force_login(segreteria)
        response = client.post(
            "/anagrafica/importazioni-autorizzazioni/nuova/", {"file": [_file_pdf()]}
        )

        assert response.status_code == 200
        assert ImportazioneAutorizzazioni.objects.count() == 0

    def test_conferma_dopo_anteprima_scrive(self, client, segreteria, capo, gruppo):
        client.force_login(segreteria)
        client.post("/anagrafica/importazioni-autorizzazioni/nuova/", {"file": [_file_pdf()]})

        response = client.post("/anagrafica/importazioni-autorizzazioni/conferma/")

        assert response.status_code == 302
        assert ImportazioneAutorizzazioni.objects.count() == 1
        gruppo.refresh_from_db()
        assert gruppo.data_autorizzazione == datetime.date(2026, 1, 15)

    def test_conferma_senza_anteprima_non_scrive(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post("/anagrafica/importazioni-autorizzazioni/conferma/")

        assert response.status_code == 302
        assert ImportazioneAutorizzazioni.objects.count() == 0

    def test_conferma_con_sessione_di_altro_utente_non_scrive(self, client, segreteria, capo):
        client.force_login(segreteria)
        client.post("/anagrafica/importazioni-autorizzazioni/nuova/", {"file": [_file_pdf()]})

        altra_segreteria = _persona("altra-segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=altra_segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        _con_mfa_configurata(altra_segreteria)
        client.force_login(altra_segreteria)

        response = client.post("/anagrafica/importazioni-autorizzazioni/conferma/")

        assert response.status_code == 302
        assert ImportazioneAutorizzazioni.objects.count() == 0

    def test_conferma_riparsa_da_zero_i_bytes_di_sessione(self, client, segreteria, capo, gruppo):
        """La conferma non deve fidarsi di un piano già calcolato: se lo stato
        del database cambia fra anteprima e conferma (qui: l'autorizzazione
        viene già registrata come più recente nel frattempo), la conferma
        deve rifiutare l'applicazione invece di scrivere comunque."""
        client.force_login(segreteria)
        client.post("/anagrafica/importazioni-autorizzazioni/nuova/", {"file": [_file_pdf()]})

        gruppo.data_autorizzazione = datetime.date(2026, 6, 1)
        gruppo.save()

        client.post("/anagrafica/importazioni-autorizzazioni/conferma/")

        assert (
            ImportazioneAutorizzazioni.objects.filter(conteggi__gruppi_applicati__gt=0).count() == 0
        )
