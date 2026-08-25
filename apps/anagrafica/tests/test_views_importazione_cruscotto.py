"""Cruscotto import unificato (M3 del piano di sviluppo): aggregazione in
sola lettura di ImportazioneCSV e ImportazioneAutorizzazioni, stesso
perimetro RUOLI_IMPORT_ANAGRAFICA dei due flussi esistenti."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.base import ContentFile

from apps.accounts.models import Delega, Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import ImportazioneAutorizzazioni, ImportazioneCSV

pytestmark = pytest.mark.django_db


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


class TestPerimetro:
    def test_accesso_negato_senza_ruolo(self, client):
        utente = _persona("senza-ruolo@campania.agesci.it")
        _con_mfa_configurata(utente)
        client.force_login(utente)
        response = client.get("/anagrafica/importazioni/cruscotto/")
        assert response.status_code == 403

    def test_accesso_negato_anonimo(self, client):
        response = client.get("/anagrafica/importazioni/cruscotto/")
        assert response.status_code == 302

    def test_accesso_consentito_a_segreteria(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/importazioni/cruscotto/")
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
        response = client.get("/anagrafica/importazioni/cruscotto/")
        assert response.status_code == 200


class TestAggregazione:
    def test_elenca_entrambi_i_tipi_in_ordine_cronologico(self, client, segreteria):
        csv_import = ImportazioneCSV.objects.create(
            file=ContentFile(b"x", name="a.csv"),
            anno_scout=2026,
            anomalie=[],
        )
        pdf_import = ImportazioneAutorizzazioni.objects.create(
            anno_scout=2026,
            anomalie=[{"livello": "errore", "dettaglio": "qualcosa"}],
        )

        client.force_login(segreteria)
        response = client.get("/anagrafica/importazioni/cruscotto/")

        righe = response.context["righe"]
        assert [r["importazione"] for r in righe] == [pdf_import, csv_import]
        assert [r["tipo"] for r in righe] == ["Autorizzazioni PDF", "CSV anagrafica"]

    def test_badge_anomalie_riflette_il_campo_anomalie(self, client, segreteria):
        ImportazioneCSV.objects.create(
            file=ContentFile(b"x", name="a.csv"), anno_scout=2026, anomalie=[]
        )
        ImportazioneAutorizzazioni.objects.create(
            anno_scout=2026, anomalie=[{"livello": "errore", "dettaglio": "qualcosa"}]
        )

        client.force_login(segreteria)
        response = client.get("/anagrafica/importazioni/cruscotto/")

        righe = {r["tipo"]: r["con_anomalie"] for r in response.context["righe"]}
        assert righe["CSV anagrafica"] is False
        assert righe["Autorizzazioni PDF"] is True

    def test_lista_vuota_non_esplode(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/importazioni/cruscotto/")
        assert response.status_code == 200
        assert response.context["righe"] == []
