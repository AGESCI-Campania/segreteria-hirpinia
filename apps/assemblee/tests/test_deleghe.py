"""Deleghe degli AE (apps/assemblee/deleghe.py, regolamento art. 5)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo, FunzioneIncarico, IncaricoUnita
from apps.assemblee import deleghe, elenco, sedute
from apps.assemblee import file as file_assemblea
from apps.assemblee.models import (
    Assemblea,
    DelegaAE,
    OperatoreVoto,
    Provenienza,
    Seduta,
    TipoAssemblea,
)
from apps.assemblee.quorum import stato_quorum
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


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
def avellino() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def ariano() -> Gruppo:
    return Gruppo.objects.create(codice="E2913", nome="ARIANO 1")


def _capo(codice, gruppo, funzione=None) -> Capo:
    capo = Capo.objects.create(codice_socio=codice, nome="Nome", cognome=codice)
    CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    if funzione:
        IncaricoUnita.objects.create(
            capo=capo, anno_scout=2026, gruppo_servizio=gruppo, funzione=funzione
        )
    return capo


@pytest.fixture
def assemblea(segreteria, avellino, ariano) -> Assemblea:
    _capo("AE_AV", avellino, FunzioneIncarico.AE_GRUPPO)
    _capo("AEU_AV", avellino, FunzioneIncarico.AE_UNITA)
    _capo("CAPO_AV", avellino, FunzioneIncarico.CAPO_UNITA)
    _capo("CAPO2_AV", avellino, FunzioneIncarico.CAPO_UNITA)
    _capo("AE_AR", ariano, FunzioneIncarico.AE_GRUPPO)
    _capo("CAPO_AR", ariano, FunzioneIncarico.CAPO_UNITA)
    _capo("AE_ZONA", ariano)
    _capo("RDZ", ariano)
    _capo("COMITATO", avellino)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    a = _per_codice(assemblea, "AE_ZONA")
    deleghe.aggiorna_qualifiche(a, segreteria, ae_zona=True, rdz=False, comitato=False)
    deleghe.aggiorna_qualifiche(
        _per_codice(assemblea, "RDZ"), segreteria, ae_zona=False, rdz=True, comitato=False
    )
    deleghe.aggiorna_qualifiche(
        _per_codice(assemblea, "COMITATO"), segreteria, ae_zona=False, rdz=False, comitato=True
    )
    return assemblea


@pytest.fixture
def seduta(assemblea, segreteria) -> Seduta:
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    return seduta


def _per_codice(assemblea, codice):
    return assemblea.aventi_diritto.get(codice_socio=codice)


def _delega(seduta, segreteria, delegante, delegato):
    a = seduta.assemblea
    return deleghe.registra_delega(
        seduta, _per_codice(a, delegante), _per_codice(a, delegato), segreteria
    )


class TestChiPuoDelegare:
    def test_ae_di_gruppo_dagli_incarichi(self, assemblea):
        possono = {a.codice_socio for a in deleghe.possono_delegare(assemblea.aventi_diritto.all())}
        assert possono == {"AE_AV", "AE_AR", "AE_ZONA"}

    def test_ae_di_gruppo_dichiarato_per_un_inserito_a_mano(self, assemblea, segreteria, avellino):
        nuovo = elenco.inserisci(
            assemblea,
            segreteria,
            nome="Don",
            cognome="Nuovo",
            gruppo=avellino,
            provenienza=Provenienza.NON_NOTA,
            incarichi=[{"funzione": FunzioneIncarico.AE_GRUPPO}],
        )
        assert deleghe.e_ae_gruppo(nuovo)

    def test_ae_di_unita_non_delega(self, seduta, segreteria):
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AEU_AV", "CAPO_AV")


class TestDestinatari:
    def test_ae_di_gruppo_a_un_capo_del_suo_gruppo(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "CAPO_AV")

    def test_ae_di_gruppo_a_un_altro_ae(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "AE_ZONA")

    def test_ae_di_gruppo_non_a_un_capo_di_altro_gruppo(self, seduta, segreteria):
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AE_AV", "CAPO_AR")

    @pytest.mark.parametrize("delegato", ["RDZ", "COMITATO"])
    def test_ae_di_zona_a_rdz_o_comitato(self, seduta, segreteria, delegato):
        _delega(seduta, segreteria, "AE_ZONA", delegato)

    def test_ae_di_zona_non_a_un_capo_qualsiasi(self, seduta, segreteria):
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AE_ZONA", "CAPO_AR")


class TestLimiti:
    def test_una_sola_delega_per_delegato(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "AE_ZONA")
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AE_AR", "AE_ZONA")

    def test_un_ae_delega_una_volta(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "CAPO_AV")
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AE_AV", "CAPO2_AV")

    def test_chi_ha_delegato_non_riceve(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AR", "AE_ZONA")
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AE_AV", "AE_AR")

    def test_chi_ha_ricevuto_non_delega(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "AE_ZONA")
        with pytest.raises(ValidationError):
            _delega(seduta, segreteria, "AE_ZONA", "RDZ")

    def test_solo_gestori_e_operatori(self, seduta):
        with pytest.raises(PermissionDenied):
            _delega(seduta, _persona("capo@example.it"), "AE_AV", "CAPO_AV")

    def test_l_operatore_registra(self, seduta, assemblea):
        operatore = _persona("op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        _delega(seduta, operatore, "AE_AV", "CAPO_AV")


class TestQualifiche:
    def test_rdz_e_anche_comitato(self, assemblea):
        assert _per_codice(assemblea, "RDZ").comitato

    def test_un_solo_ae_di_zona(self, assemblea, segreteria):
        with pytest.raises(ValidationError):
            deleghe.aggiorna_qualifiche(
                _per_codice(assemblea, "CAPO_AR"),
                segreteria,
                ae_zona=True,
                rdz=False,
                comitato=False,
            )


class TestPresenzaPerDelega:
    def _registra(self, seduta, segreteria, *codici):
        for codice in codici:
            sedute.registra_presenza(seduta, _per_codice(seduta.assemblea, codice), segreteria)

    def test_il_delegante_conta_se_il_delegato_e_presente(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "CAPO_AV")
        assert stato_quorum(seduta).presenti == 0
        self._registra(seduta, segreteria, "CAPO_AV")
        assert stato_quorum(seduta).presenti == 2

    def test_pagina_presenze_mostra_il_delegante_presente_per_delega(
        self, client, seduta, segreteria
    ):
        _delega(seduta, segreteria, "AE_AV", "CAPO_AV")
        ae = _per_codice(seduta.assemblea, "AE_AV")
        url = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/presenze/"
        client.force_login(segreteria)
        risposta = client.get(url)
        assert ae.pk not in risposta.context["per_delega"]
        assert "(non ancora presente)" in risposta.content.decode()

        self._registra(seduta, segreteria, "CAPO_AV")
        risposta = client.get(url)
        assert risposta.context["per_delega"][ae.pk].codice_socio == "CAPO_AV"
        pagina = risposta.content.decode()
        assert "Presente per delega" in pagina and "Presente di persona" in pagina
        # Fra i «solo non ancora presenti» il delegante non compare.
        assenti = client.get(url, {"assenti": "1"}).context["righe"]
        assert ae not in list(assenti)

    def test_presente_anche_di_persona_conta_una_volta(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "CAPO_AV")
        self._registra(seduta, segreteria, "CAPO_AV", "AE_AV")
        assert stato_quorum(seduta).presenti == 2

    def test_tracciato_con_codice_delegato_e_presente(self, seduta, segreteria):
        _delega(seduta, segreteria, "AE_AV", "CAPO_AV")
        self._registra(seduta, segreteria, "CAPO_AV")
        righe = {r[2]: r for r in file_assemblea.righe_tracciato(seduta.assemblea)}
        assert righe["AE_AV"][16] == "SI"
        assert righe["AE_AV"][18] == "CAPO_AV"
        assert righe["CAPO_AV"][18] is None


class TestViste:
    def test_registra_e_revoca_dalla_pagina(self, client, seduta, segreteria):
        client.force_login(segreteria)
        base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/deleghe/"
        delegante = _per_codice(seduta.assemblea, "AE_AV")
        delegato = _per_codice(seduta.assemblea, "CAPO_AV")
        client.post(base, {"delegante": delegante.pk, "delegato": delegato.pk})
        delega = DelegaAE.objects.get()
        assert (delega.delegante, delega.delegato) == (delegante, delegato)

        client.post(f"{base}{delega.pk}/revoca/")
        assert not DelegaAE.objects.exists()

    def test_errore_di_regola_mostrato_nel_form(self, client, seduta, segreteria):
        client.force_login(segreteria)
        base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/deleghe/"
        response = client.post(
            base,
            {
                "delegante": _per_codice(seduta.assemblea, "AE_AV").pk,
                "delegato": _per_codice(seduta.assemblea, "CAPO_AR").pk,
            },
        )
        assert response.status_code == 200
        assert response.context["form"].non_field_errors()
        assert not DelegaAE.objects.exists()
