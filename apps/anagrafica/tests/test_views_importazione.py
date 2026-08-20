"""Test delle viste di import CSV: perimetro e flusso anteprima→conferma."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Delega, Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, ImportazioneCSV

pytestmark = pytest.mark.django_db

HEADER = (
    "ANNO SCOUT,CODICE SOCIO,NOME,COGNOME,SESSO,DATA NASCITA,COMUNE NASCITA,"
    "CODICE FISCALE,NAZIONALITA,INDIRIZZO,CIVICO,COMUNE RESIDENZA,"
    "PROVINCIA RESIDENZA,CAP,EMAIL,CELLULARE,PROFESSIONE,LIVELLO FOCA,"
    "INGRESSO COCA,COMUNITA SOCIO,STATUS SOCIO,GRUPPO,ORDINALE,EMAIL GRUPPO,"
    "INDIRIZZO GRUPPO,CIVICO GRUPPO,CAP GRUPPO,RESIDENZA GRUPPO,"
    "PROVINCIA GRUPPO,TELEFONO GRUPPO,CODICE FISCALE GRUPPO,PARROCCHIA GRUPPO,"
    "DIOCESI GRUPPO,DENOM. SOCIALE GRUPPO"
)


def _riga(*, codice_socio="10001") -> str:
    campi = [
        '="2026"',
        f'="{codice_socio}"',
        '="MARIO"',
        '="ROSSI"',
        '="M"',
        "01/01/1980",
        '="AVELLINO"',
        '="RSSMRA80A01A509X"',
        '="ITALIA"',
        '="VIA ROMA"',
        '="1"',
        '="AVELLINO"',
        '="AV"',
        '="83100"',
        '="socio@example.org"',
        '="3331234567"',
        '="IMPIEGATO"',
        '="3"',
        '="2010"',
        '="CLAN"',
        '="RINNOVO ADESIONE"',
        '="AVELLINO 1"',
        '="E0133"',
        '="avellino1@campania.agesci.it"',
        '="VIA GRUPPO"',
        '="2"',
        '="83100"',
        '="AVELLINO"',
        '="AV"',
        '="0825000000"',
        '="00000000000"',
        '="SAN MODESTINO"',
        '="AVELLINO"',
        '="AGESCI AVELLINO 1"',
        "",
    ]
    return ",".join(campi)


def _csv_testo(*righe: str) -> str:
    return "sep=,\n" + HEADER + "\n" + "\n".join(righe) + "\n"


def _file_csv() -> SimpleUploadedFile:
    testo = _csv_testo(_riga())
    return SimpleUploadedFile("ricercasoci.csv", testo.encode("utf-8-sig"), content_type="text/csv")


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def utente_senza_ruolo() -> Utente:
    return _persona("senza-ruolo@campania.agesci.it")


class TestPerimetro:
    def test_accesso_negato_senza_ruolo(self, client, utente_senza_ruolo):
        client.force_login(utente_senza_ruolo)
        response = client.get("/anagrafica/importazioni/")
        assert response.status_code == 403

    def test_accesso_negato_anonimo(self, client):
        response = client.get("/anagrafica/importazioni/")
        assert response.status_code == 302  # redirect al login

    def test_accesso_consentito_a_segreteria(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/importazioni/")
        assert response.status_code == 200

    def test_accesso_consentito_per_delega(self, client, segreteria):
        delegato = _persona("delegato@campania.agesci.it")
        ruolo = Ruolo.objects.get(utente=segreteria)
        Delega.objects.create(
            delegante=segreteria,
            delegato=delegato,
            ruolo=ruolo,
            data_fine=datetime.date.today() + datetime.timedelta(days=30),
        )
        client.force_login(delegato)
        response = client.get("/anagrafica/importazioni/")
        assert response.status_code == 200


class TestFlussoAnteprimaConferma:
    def test_anteprima_non_scrive_nulla(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post("/anagrafica/importazioni/nuova/", {"file": _file_csv()})

        assert response.status_code == 200
        assert Capo.objects.count() == 0
        assert ImportazioneCSV.objects.count() == 0

    def test_conferma_dopo_anteprima_scrive(self, client, segreteria):
        client.force_login(segreteria)
        client.post("/anagrafica/importazioni/nuova/", {"file": _file_csv()})

        response = client.post("/anagrafica/importazioni/conferma/")

        assert response.status_code == 302
        assert Capo.objects.count() == 1
        assert ImportazioneCSV.objects.count() == 1

    def test_conferma_senza_anteprima_non_scrive(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post("/anagrafica/importazioni/conferma/")

        assert response.status_code == 302
        assert ImportazioneCSV.objects.count() == 0

    def test_conferma_con_sessione_di_altro_utente_non_scrive(self, client, segreteria):
        client.force_login(segreteria)
        client.post("/anagrafica/importazioni/nuova/", {"file": _file_csv()})

        altra_segreteria = _persona("altra-segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=altra_segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        _con_mfa_configurata(altra_segreteria)
        client.force_login(altra_segreteria)

        response = client.post("/anagrafica/importazioni/conferma/")

        assert response.status_code == 302
        assert ImportazioneCSV.objects.count() == 0
