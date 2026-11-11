"""Comitato elettorale (comitato.py): componenti dall'elenco, account e
invito di attivazione, verbale."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import InvitoAttivazione, Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import comitato, elenco, sedute, verbale
from apps.assemblee.models import Assemblea, AventeDiritto, OperatoreVoto, Seduta, TipoAssemblea
from apps.assemblee.permessi import assemblee_visibili, puo_operare
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def assemblea(segreteria) -> Assemblea:
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for i in range(3):
        capo = Capo.objects.create(
            codice_socio=f"10{i}", nome="Nome", cognome=f"Capo{i}", email=f"capo{i}@example.it"
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _avente(assemblea, codice: str) -> AventeDiritto:
    return assemblea.aventi_diritto.get(codice_socio=codice)


class TestAggiungi:
    def test_crea_account_senza_password_e_invia_invito(self, assemblea, segreteria):
        avente = _avente(assemblea, "100")
        componente, inviato = comitato.aggiungi(assemblea, avente, segreteria)

        assert inviato
        utente = componente.utente
        assert utente.email == "capo0@example.it"
        assert utente.codice_socio == "100"
        assert utente.tipo == TipoUtente.PERSONA
        assert not utente.has_usable_password()
        assert InvitoAttivazione.objects.filter(email="capo0@example.it").exists()
        assert mail.outbox[-1].to == ["capo0@example.it"]
        assert puo_operare(utente, assemblea)
        assert list(assemblee_visibili(utente)) == [assemblea]

    def test_account_esistente_si_riusa_senza_invito(self, assemblea, segreteria):
        esistente = Utente.objects.create(
            username="x", email="altra@example.it", codice_socio="101", stato=StatoUtente.ATTIVO
        )
        esistente.set_password("una-password-qualsiasi")
        esistente.save()

        componente, inviato = comitato.aggiungi(assemblea, _avente(assemblea, "101"), segreteria)

        assert componente.utente == esistente
        assert not inviato
        assert Utente.objects.count() == 2
        assert not mail.outbox

    def test_senza_accesso_niente_account(self, assemblea, segreteria):
        componente, inviato = comitato.aggiungi(
            assemblea, _avente(assemblea, "102"), segreteria, accesso=False
        )
        assert componente.utente is None
        assert not inviato
        assert not Utente.objects.filter(email="capo2@example.it").exists()

    def test_senza_email_serve_aggiungerlo_senza_accesso(self, assemblea, segreteria):
        avente = _avente(assemblea, "100")
        avente.email = ""
        avente.save()
        with pytest.raises(ValidationError):
            comitato.aggiungi(assemblea, avente, segreteria)
        assert not OperatoreVoto.objects.exists()
        comitato.aggiungi(assemblea, avente, segreteria, accesso=False)
        assert OperatoreVoto.objects.count() == 1

    def test_email_di_un_account_di_gruppo(self, assemblea, segreteria):
        gruppo = Gruppo.objects.get(codice="E0133")
        Utente.objects.create(
            username="g", email="capo0@example.it", tipo=TipoUtente.GRUPPO, gruppo=gruppo
        )
        avente = _avente(assemblea, "100")
        avente.codice_socio = ""
        avente.save()
        with pytest.raises(ValidationError):
            comitato.aggiungi(assemblea, avente, segreteria)
        assert not OperatoreVoto.objects.exists()

    def test_due_volte_lo_stesso_capo(self, assemblea, segreteria):
        avente = _avente(assemblea, "100")
        comitato.aggiungi(assemblea, avente, segreteria, accesso=False)
        with pytest.raises(ValidationError):
            comitato.aggiungi(assemblea, avente, segreteria)

    def test_solo_aventi_dell_elenco(self, assemblea, segreteria):
        avente = _avente(assemblea, "100")
        elenco.elimina([avente], segreteria)
        avente.refresh_from_db()
        with pytest.raises(ValidationError):
            comitato.aggiungi(assemblea, avente, segreteria)
        altra = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        with pytest.raises(ValidationError):
            comitato.aggiungi(altra, _avente(assemblea, "101"), segreteria)

    def test_solo_i_gestori_e_non_a_assemblea_conclusa(self, assemblea, segreteria):
        capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
        with pytest.raises(PermissionDenied):
            comitato.aggiungi(assemblea, _avente(assemblea, "100"), capo)
        assemblea.conclusa_il = timezone.now()
        assemblea.save()
        with pytest.raises(ValidationError):
            comitato.aggiungi(assemblea, _avente(assemblea, "100"), segreteria)

    def test_invito_non_partito_lascia_la_nomina(self, assemblea, segreteria, monkeypatch):
        def fallisce(**kwargs):
            raise RuntimeError("smtp giù")

        monkeypatch.setattr(comitato, "crea_invito", fallisce)
        with pytest.raises(comitato.InvitoNonInviato):
            comitato.aggiungi(assemblea, _avente(assemblea, "100"), segreteria)
        componente = OperatoreVoto.objects.get()
        assert componente.utente is not None


class TestAccessoERimozione:
    def test_accesso_dato_dopo(self, assemblea, segreteria):
        componente, _ = comitato.aggiungi(
            assemblea, _avente(assemblea, "100"), segreteria, accesso=False
        )
        assert comitato.dai_accesso(componente, segreteria)
        componente.refresh_from_db()
        assert componente.utente.email == "capo0@example.it"

    def test_nuovo_invito_revoca_il_precedente(self, assemblea, segreteria):
        componente, _ = comitato.aggiungi(assemblea, _avente(assemblea, "100"), segreteria)
        assert comitato.dai_accesso(componente, segreteria)
        assert InvitoAttivazione.objects.filter(email="capo0@example.it").count() == 2
        assert (
            InvitoAttivazione.objects.filter(email="capo0@example.it", stato="INVIATO").count() == 1
        )

    def test_rimozione_lascia_l_account_ma_toglie_l_accesso(self, assemblea, segreteria):
        componente, _ = comitato.aggiungi(assemblea, _avente(assemblea, "100"), segreteria)
        utente = componente.utente
        comitato.rimuovi(componente, segreteria)
        assert Utente.objects.filter(pk=utente.pk).exists()
        assert not puo_operare(utente, assemblea)


class TestViste:
    def test_autocompletamento_solo_elenco_e_niente_recapiti(self, client, assemblea, segreteria):
        comitato.aggiungi(assemblea, _avente(assemblea, "101"), segreteria, accesso=False)
        client.force_login(segreteria)
        risposta = client.get(f"/assemblee/{assemblea.pk}/comitato/cerca/", {"q": "capo"}).json()
        cognomi = [r["cognome"] for r in risposta["risultati"]]
        assert cognomi == ["Capo0", "Capo2"]
        assert set(risposta["risultati"][0]) == {"id", "nome", "cognome", "gruppo"}

    def test_autocompletamento_solo_gestori(self, client, assemblea):
        capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
        client.force_login(capo)
        assert client.get(f"/assemblee/{assemblea.pk}/comitato/cerca/?q=capo").status_code == 403

    def test_aggiunta_e_rimozione_dalla_pagina(self, client, assemblea, segreteria):
        avente = _avente(assemblea, "100")
        client.force_login(segreteria)
        client.post(
            f"/assemblee/{assemblea.pk}/comitato/aggiungi/", {"avente": avente.pk, "accesso": "on"}
        )
        componente = OperatoreVoto.objects.get()
        assert componente.avente == avente and componente.utente is not None
        pagina = client.get(f"/assemblee/{assemblea.pk}/").content.decode()
        assert "Capo0 Nome" in pagina and "Invito da attivare" in pagina

        client.post(f"/assemblee/{assemblea.pk}/comitato/{componente.pk}/rimuovi/")
        assert not OperatoreVoto.objects.exists()


def test_comitato_nel_verbale(assemblea, segreteria):
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    for avente in assemblea.aventi_diritto.all():
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    comitato.aggiungi(assemblea, _avente(assemblea, "100"), segreteria, accesso=False)
    comitato.aggiungi(assemblea, _avente(assemblea, "102"), segreteria)

    contesto = verbale.contesto_verbale(seduta)
    assert contesto["comitato_elettorale"] == ["Capo0 Nome", "Capo2 Nome"]
