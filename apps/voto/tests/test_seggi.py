"""Seggi e modalità «solo seggi» (apps/voto/postazioni.py)."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.assemblee import sedute, votazioni
from apps.assemblee.models import ModalitaVoto, TipoVotazione
from apps.voto import codici, postazioni, urna
from apps.voto.models import Postazione, Scheda

from .conftest import avente, persona

pytestmark = pytest.mark.django_db


@pytest.fixture
def costituita(seduta, assemblea, segreteria):
    for cognome in ("Rossi", "Bianchi", "Verdi"):
        sedute.registra_presenza(seduta, avente(assemblea, cognome), segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


@pytest.fixture
def elezione(costituita, assemblea, segreteria):
    votazione = votazioni.apri_votazione(
        costituita,
        segreteria,
        tipo=TipoVotazione.ELEZIONE,
        oggetto="Elezione",
        incarico="X",
        candidati=["Tizio"],
    )
    votazione.aperta_in_app_il = timezone.now()
    votazione.save()
    return votazione


def _attiva(client, seduta, utente) -> Postazione:
    postazione, segreto = postazioni.crea(seduta, "Seggio 1", utente)
    client.post("/voto/seggio/", {"segreto": segreto})
    postazione.refresh_from_db()
    return postazione


class TestPostazioni:
    def test_link_monouso_e_solo_hash(self, costituita, segreteria):
        postazione, segreto = postazioni.crea(costituita, " Seggio  1 ", segreteria)
        assert postazione.nome == "Seggio 1"
        assert segreto not in postazione.attivazione_hash
        _, cookie = postazioni.attiva(segreto)
        assert postazioni.attiva(segreto) is None
        postazione.refresh_from_db()
        assert cookie.split(":", 1)[1] not in postazione.token_hash
        assert postazioni.dal_cookie(cookie) == postazione

    def test_cookie_falso_o_disattivato(self, costituita, segreteria):
        postazione, segreto = postazioni.crea(costituita, "Seggio 1", segreteria)
        _, cookie = postazioni.attiva(segreto)
        assert postazioni.dal_cookie(f"{postazione.pk}:falso") is None
        assert postazioni.dal_cookie("spazzatura") is None
        postazioni.disattiva(postazione, segreteria)
        assert postazioni.dal_cookie(cookie) is None

    def test_solo_chi_opera(self, costituita):
        with pytest.raises(PermissionDenied):
            postazioni.crea(costituita, "Seggio", persona("x@example.it"))

    def test_nome_obbligatorio(self, costituita, segreteria):
        with pytest.raises(ValidationError):
            postazioni.crea(costituita, "  ", segreteria)


class TestSoloSeggio:
    @pytest.fixture(autouse=True)
    def solo_seggio(self, assemblea):
        assemblea.modalita_voto = ModalitaVoto.SOLO_SEGGIO
        assemblea.save()

    def test_dal_telefono_rifiutato(self, elezione, costituita, assemblea, segreteria):
        codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        codice = codici.codice_attivo(costituita, avente(assemblea, "Rossi"))
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])

    def test_dal_seggio_accettato(self, elezione, costituita, assemblea, segreteria):
        postazione, segreto = postazioni.crea(costituita, "Seggio 1", segreteria)
        postazioni.attiva(segreto)
        postazione.refresh_from_db()
        codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        codice = codici.codice_attivo(costituita, avente(assemblea, "Rossi"))
        urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)], postazione)
        assert Scheda.objects.count() == 1

    def test_accesso_dal_telefono_rifiutato(self, client, costituita, assemblea, segreteria):
        codice = codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        risposta = client.post("/voto/accedi/", {"codice": codice}, follow=True)
        assert "solo ai seggi" in risposta.content.decode()


class TestChiosco:
    def test_voto_al_seggio_e_azzeramento(
        self, client, elezione, costituita, assemblea, segreteria
    ):
        _attiva(client, costituita, segreteria)
        assert "Seggio 1" in client.get("/voto/").content.decode()
        for cognome in ("Rossi", "Bianchi"):
            codice = codici.emetti(costituita, avente(assemblea, cognome), segreteria)
            client.post("/voto/accedi/", {"codice": codice})
            ricevuta = client.post(
                "/voto/scheda/",
                {
                    "votazioni": str(elezione.pk),
                    "azione": "conferma",
                    f"esito_{elezione.pk}_0": "BIANCA",
                },
            )
            testo = ricevuta.content.decode()
            assert 'http-equiv="refresh" content="30;' in testo
            # Il pulsante di chiusura è in cima e in fondo alla ricevuta.
            assert testo.count("Fatto, avanti il prossimo") == 2
            # Il voto successivo riparte dall'accesso: nessuna sessione residua.
            assert client.get("/voto/scheda/").url == "/voto/"
        assert Scheda.objects.count() == 2

    def test_pagina_seggi(self, client, costituita, assemblea, operatore):
        client.force_login(operatore)
        url = f"/voto/gestione/{assemblea.pk}/sedute/{costituita.pk}/seggi/"
        risposta = client.post(url, {"nome": "Seggio A"})
        testo = risposta.content.decode()
        assert "/voto/seggio/#s=" in testo and 'src="data:image/svg+xml' in testo
        assert "no-store" in risposta["Cache-Control"]
        postazione = Postazione.objects.get()
        client.post(url, {"disattiva": postazione.pk})
        postazione.refresh_from_db()
        assert not postazione.attiva


def test_al_seggio_l_accesso_scade(client, elezione, costituita, assemblea, segreteria):
    from unittest.mock import patch

    from apps.voto import views_urna

    _attiva(client, costituita, segreteria)
    codice = codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
    client.post("/voto/accedi/", {"codice": codice})
    assert client.get("/voto/scheda/").status_code == 200
    adesso = views_urna.time.time()
    with patch.object(
        views_urna.time, "time", return_value=adesso + views_urna.SECONDI_ACCESSO_SEGGIO + 1
    ):
        assert client.get("/voto/scheda/").url == "/voto/"
