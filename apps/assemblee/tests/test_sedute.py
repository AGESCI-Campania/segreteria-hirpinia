"""Sedute, presenze e quorum costitutivo (apps/assemblee/sedute.py e quorum.py, D-70)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, sedute
from apps.assemblee import file as file_assemblea
from apps.assemblee.models import (
    Appello,
    Assemblea,
    OperatoreVoto,
    Presenza,
    Provenienza,
    Seduta,
    TipoAppello,
    TipoAssemblea,
)
from apps.assemblee.quorum import appello_effettivo, meta_piu_uno, stato_quorum
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

GIORNO = datetime.date(2026, 11, 22)


def _persona(email: str, ruolo: str | None = None) -> Utente:
    n = Utente.objects.count()
    utente = Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    return _persona("segreteria@campania.agesci.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def operatore(assemblea) -> Utente:
    utente = _persona("operatore@example.it")
    OperatoreVoto.objects.create(assemblea=assemblea, utente=utente)
    return utente


@pytest.fixture
def avellino() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def assemblea(segreteria, avellino) -> Assemblea:
    """Cinque aventi diritto: quattro censiti (app) e uno inserito a mano (carta)."""
    for i in range(1, 5):
        capo = Capo.objects.create(codice_socio=str(i), nome="Nome", cognome=f"Cognome{i}")
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=avellino)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=GIORNO)
    elenco.importa_elenco(assemblea, segreteria)
    elenco.inserisci(
        assemblea,
        segreteria,
        nome="Sara",
        cognome="Neri",
        gruppo=avellino,
        provenienza=Provenienza.NON_NOTA,
    )
    return assemblea


@pytest.fixture
def prima(assemblea) -> Seduta:
    return assemblea.sedute.get(convocazione=1)


def _presenti(seduta: Seduta, utente: Utente, *cognomi: str) -> None:
    for cognome in cognomi:
        avente = seduta.assemblea.aventi_diritto.get(cognome=cognome)
        sedute.registra_presenza(seduta, avente, utente)


class TestMetaPiuUno:
    @pytest.mark.parametrize("n,atteso", [(187, 94), (186, 94), (5, 3), (4, 3), (1, 1)])
    def test_valori(self, n, atteso):
        assert meta_piu_uno(n) == atteso


class TestPresenze:
    def test_apertura_crea_l_appello_d_ingresso(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        appello = prima.appelli.get()
        assert appello.tipo == TipoAppello.INGRESSO
        assert prima.aperta
        with pytest.raises(ValidationError):
            sedute.apri_seduta(prima, operatore)

    def test_registrazione_e_quorum(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        _presenti(prima, operatore, "Cognome1", "Cognome2", "Neri")
        stato = stato_quorum(prima)
        assert (stato.aventi_diritto, stato.presenti, stato.soglia) == (5, 3, 3)
        assert (stato.presenti_app, stato.presenti_carta) == (2, 1)
        assert stato.raggiunto

    def test_doppio_tocco_non_duplica(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        avente = prima.assemblea.aventi_diritto.get(cognome="Cognome1")
        assert sedute.registra_presenza(prima, avente, operatore)
        assert not sedute.registra_presenza(prima, avente, operatore)
        assert Presenza.objects.count() == 1

    def test_annulla(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        _presenti(prima, operatore, "Cognome1")
        sedute.annulla_presenza(
            prima, prima.assemblea.aventi_diritto.get(cognome="Cognome1"), operatore
        )
        assert stato_quorum(prima).presenti == 0

    def test_seduta_non_aperta(self, prima, operatore):
        with pytest.raises(ValidationError):
            _presenti(prima, operatore, "Cognome1")

    def test_eliminato_non_si_registra_e_non_conta(self, prima, operatore, segreteria):
        sedute.apri_seduta(prima, operatore)
        _presenti(prima, operatore, "Cognome1")
        elenco.elimina([prima.assemblea.aventi_diritto.get(cognome="Cognome1")], segreteria)
        assert stato_quorum(prima).presenti == 0
        assert stato_quorum(prima).aventi_diritto == 4
        with pytest.raises(ValidationError):
            _presenti(prima, operatore, "Cognome1")

    def test_solo_gestori_e_operatori(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        with pytest.raises(PermissionDenied):
            _presenti(prima, _persona("capo@example.it"), "Cognome1")

    def test_verifica_aperta_non_e_ancora_effettiva(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        ingresso = prima.appelli.get()
        verifica = Appello.objects.create(seduta=prima, numero=2, tipo=TipoAppello.VERIFICA)
        assert appello_effettivo(prima) == ingresso
        verifica.chiuso_il = timezone.now()
        verifica.save()
        assert appello_effettivo(prima) == verifica


class TestEsitoSeduta:
    def test_costituita_con_quorum_e_chiusura_lavori(self, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        _presenti(prima, operatore, "Cognome1", "Cognome2", "Cognome3")
        with pytest.raises(ValidationError):
            sedute.dichiara_non_costituita(prima, operatore)
        sedute.dichiara_costituita(prima, operatore)
        assert prima.costituita is True and prima.aperta
        sedute.chiudi_lavori(prima, operatore)
        assert not prima.aperta

    def test_senza_quorum_e_nuova_convocazione(self, prima, operatore, segreteria):
        sedute.apri_seduta(prima, operatore)
        _presenti(prima, operatore, "Cognome1")
        with pytest.raises(ValidationError):
            sedute.dichiara_costituita(prima, operatore)
        sedute.dichiara_non_costituita(prima, operatore)
        assert prima.costituita is False and prima.chiusa_il is not None

        with pytest.raises(PermissionDenied):
            sedute.crea_convocazione_successiva(prima.assemblea, operatore, data=GIORNO)
        seconda = sedute.crea_convocazione_successiva(prima.assemblea, segreteria, data=GIORNO)
        assert seconda.convocazione == 2
        # Presenze da capo: la seconda convocazione parte senza presenti.
        sedute.apri_seduta(seconda, operatore)
        assert stato_quorum(seconda).presenti == 0

    def test_terza_convocazione_senza_quorum(self, prima, operatore, segreteria):
        assemblea = prima.assemblea
        for _ in range(2):
            seduta = sedute.seduta_corrente(assemblea)
            sedute.apri_seduta(seduta, operatore)
            sedute.dichiara_non_costituita(seduta, operatore)
            sedute.crea_convocazione_successiva(assemblea, segreteria, data=GIORNO)
        terza = sedute.seduta_corrente(assemblea)
        assert terza.convocazione == 3
        sedute.apri_seduta(terza, operatore)
        stato = stato_quorum(terza)
        assert stato.soglia is None and stato.raggiunto
        sedute.dichiara_costituita(terza, operatore)
        with pytest.raises(ValidationError):
            sedute.dichiara_non_costituita(terza, operatore)

    def test_niente_nuova_convocazione_dopo_una_seduta_costituita(
        self, prima, operatore, segreteria
    ):
        sedute.apri_seduta(prima, operatore)
        _presenti(prima, operatore, "Cognome1", "Cognome2", "Cognome3")
        sedute.dichiara_costituita(prima, operatore)
        with pytest.raises(ValidationError):
            sedute.crea_convocazione_successiva(prima.assemblea, segreteria, data=GIORNO)


def test_tracciato_segna_i_presenti(prima, operatore):
    sedute.apri_seduta(prima, operatore)
    _presenti(prima, operatore, "Cognome2")
    presenti = {r[4]: r[16] for r in file_assemblea.righe_tracciato(prima.assemblea)}
    assert presenti["Cognome2"] == "SI"
    assert presenti["Cognome1"] == "NO"


class TestViste:
    def test_apertura_e_registrazione_dalle_pagine(self, client, prima, operatore):
        client.force_login(operatore)
        base = f"/assemblee/{prima.assemblea_id}/sedute/{prima.pk}"
        client.post(f"{base}/azione/", {"azione": "apri"})
        prima.refresh_from_db()
        assert prima.aperta

        avente = prima.assemblea.aventi_diritto.get(cognome="Cognome1")
        response = client.post(f"{base}/presenze/{avente.pk}/", {"next": f"{base}/presenze/"})
        assert response.status_code == 302
        pagina = client.get(f"{base}/presenze/")
        assert avente.pk in pagina.context["presenti_ids"]
        assert pagina.context["quorum"].presenti == 1

    def test_un_capo_qualsiasi_non_registra(self, client, prima, operatore):
        sedute.apri_seduta(prima, operatore)
        client.force_login(_persona("capo@example.it"))
        avente = prima.assemblea.aventi_diritto.get(cognome="Cognome1")
        response = client.post(
            f"/assemblee/{prima.assemblea_id}/sedute/{prima.pk}/presenze/{avente.pk}/"
        )
        assert response.status_code == 404
        assert Presenza.objects.count() == 0


def test_chiusura_senza_conferma_rifiutata(client, prima, operatore):
    sedute.apri_seduta(prima, operatore)
    client.force_login(operatore)
    url = f"/assemblee/{prima.assemblea_id}/sedute/{prima.pk}/azione/"
    client.post(url, {"azione": "non_costituita"})
    prima.refresh_from_db()
    assert prima.aperta

    client.post(url, {"azione": "non_costituita", "conferma": "1"})
    prima.refresh_from_db()
    assert prima.costituita is False and not prima.aperta
