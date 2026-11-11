"""Dalle pagine del singolo avente (dati, qualifiche, trasferimento) si torna
all'elenco con gli stessi filtri da cui si è partiti."""

from urllib.parse import quote

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.assemblee import elenco
from apps.assemblee.models import Assemblea, AventeDiritto, Provenienza, TipoAssemblea
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segreteria",
        email="segreteria@campania.agesci.it",
        tipo=TipoUtente.PERSONA,
        stato=StatoUtente.ATTIVO,
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def ariano() -> Gruppo:
    return Gruppo.objects.create(codice="E2913", nome="ARIANO 1")


@pytest.fixture
def avente(segreteria, ariano) -> AventeDiritto:
    Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    return elenco.inserisci(
        assemblea,
        segreteria,
        nome="Sara",
        cognome="Neri",
        gruppo=ariano,
        provenienza=Provenienza.PASSAGGIO_CLAN,
    )


def _elenco(avente) -> str:
    return f"/assemblee/{avente.assemblea_id}/elenco/"


def _pagina(avente, nome) -> str:
    return f"{_elenco(avente)}{avente.pk}/{nome}/"


class TestRitornoAllElenco:
    def test_i_link_dell_elenco_portano_i_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        filtrato = f"{_elenco(avente)}?q=Neri&incompleti=1"
        html = client.get(filtrato).content.decode()
        for nome in ("email", "qualifiche", "trasferisci"):
            assert f"{_pagina(avente, nome)}?next={quote(filtrato, safe='/')}" in html

    def test_dati_tornano_ai_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        filtrato = f"{_elenco(avente)}?q=Neri&incompleti=1"
        pagina = client.get(_pagina(avente, "email"), {"next": filtrato}).content.decode()
        assert 'href="/assemblee/' in pagina and "?q=Neri&amp;incompleti=1" in pagina
        risposta = client.post(
            _pagina(avente, "email"), {"email": "sara@example.it", "sesso": "F", "next": filtrato}
        )
        assert risposta.url == filtrato

    def test_qualifiche_tornano_ai_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        filtrato = f"{_elenco(avente)}?usciti=1"
        risposta = client.post(_pagina(avente, "qualifiche"), {"rdz": "on", "next": filtrato})
        assert risposta.url == filtrato

    def test_trasferimento_torna_ai_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        avellino = Gruppo.objects.get(codice="E0133")
        filtrato = f"{_elenco(avente)}?gruppo={avente.gruppo_id}"
        risposta = client.post(
            _pagina(avente, "trasferisci"), {"gruppo": avellino.pk, "next": filtrato}
        )
        assert risposta.url == filtrato

    @pytest.mark.parametrize(
        "next_", ["", "https://esterno.example/", "/assemblee/", "//esterno.example/x"]
    )
    def test_senza_elenco_valido_il_gruppo_del_capo(self, client, segreteria, avente, next_):
        client.force_login(segreteria)
        risposta = client.post(_pagina(avente, "email"), {"email": "", "sesso": "F", "next": next_})
        assert risposta.url == f"{_elenco(avente)}?gruppo={avente.gruppo_id}"


def _nuovo_capo(gruppo, **altri) -> dict:
    return {
        "cognome": "Gialli",
        "nome": "Paolo",
        "gruppo": gruppo.pk,
        "provenienza": Provenienza.PASSAGGIO_CLAN,
        "incarichi-TOTAL_FORMS": "0",
        "incarichi-INITIAL_FORMS": "0",
        **altri,
    }


class TestNuovoCapo:
    def test_il_link_dell_elenco_porta_i_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        filtrato = f"{_elenco(avente)}?gruppo={avente.gruppo_id}&q=Neri"
        html = client.get(filtrato).content.decode()
        inserisci = f"/assemblee/{avente.assemblea_id}/elenco/nuovo/"
        assert f"{inserisci}?gruppo={avente.gruppo_id}&amp;next={quote(filtrato, safe='/')}" in html

    def test_torna_ai_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        avellino = Gruppo.objects.get(codice="E0133")
        filtrato = f"{_elenco(avente)}?q=Neri&incompleti=1"
        risposta = client.post(
            f"/assemblee/{avente.assemblea_id}/elenco/nuovo/",
            _nuovo_capo(avellino, next=filtrato),
        )
        assert risposta.url == filtrato

    def test_inseriscine_un_altro_conserva_i_filtri(self, client, segreteria, avente):
        client.force_login(segreteria)
        avellino = Gruppo.objects.get(codice="E0133")
        filtrato = f"{_elenco(avente)}?q=Neri"
        inserisci = f"/assemblee/{avente.assemblea_id}/elenco/nuovo/"
        risposta = client.post(inserisci, _nuovo_capo(avellino, next=filtrato, altro="1"))
        assert risposta.url == f"{inserisci}?gruppo={avellino.pk}&next={quote(filtrato, safe='')}"
        pagina = client.get(risposta.url).content.decode()
        assert 'value="/assemblee/' in pagina and "?q=Neri" in pagina

    def test_senza_next_il_gruppo_del_capo(self, client, segreteria, avente):
        client.force_login(segreteria)
        avellino = Gruppo.objects.get(codice="E0133")
        risposta = client.post(
            f"/assemblee/{avente.assemblea_id}/elenco/nuovo/", _nuovo_capo(avellino)
        )
        assert risposta.url == f"{_elenco(avente)}?gruppo={avellino.pk}"
