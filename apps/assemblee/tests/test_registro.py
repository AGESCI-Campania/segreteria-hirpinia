"""Registro delle operazioni di un'assemblea (apps/assemblee/registro.py)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from auditlog.context import set_actor
from django.utils import timezone

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, registro, sedute
from apps.assemblee.models import (
    Assemblea,
    OperatoreVoto,
    RichiedenteVerifica,
    Seduta,
    TipoAssemblea,
)
from apps.assemblee.permessi import puo_vedere_registro
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
    return _persona("segreteria@example.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def rdz() -> Utente:
    return _persona("rdz@example.it", Ruolo.Tipo.RDZ)


def _assemblea(segreteria, anno: int) -> Assemblea:
    gruppo, _ = Gruppo.objects.get_or_create(codice="E0133", defaults={"nome": "AVELLINO 1"})
    capo, _ = Capo.objects.get_or_create(
        codice_socio="1", defaults={"nome": "Mario", "cognome": "Rossi"}
    )
    CensimentoCapo.objects.get_or_create(capo=capo, anno_scout=anno - 1, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=anno)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


@pytest.fixture
def assemblea(segreteria) -> Assemblea:
    return _assemblea(segreteria, 2027)


class TestPermessi:
    @pytest.mark.parametrize(
        "ruolo,atteso",
        [
            (Ruolo.Tipo.ADMIN, True),
            (Ruolo.Tipo.RDZ, True),
            (Ruolo.Tipo.SEGRETERIA, False),
            (None, False),
        ],
    )
    def test_solo_amministratori_e_rdz(self, ruolo, atteso):
        assert puo_vedere_registro(_persona(f"{ruolo}@example.it", ruolo)) is atteso

    def test_pagina(self, client, assemblea, rdz, segreteria):
        url = f"/assemblee/{assemblea.pk}/registro/"
        client.force_login(segreteria)
        assert client.get(url).status_code == 403
        assert "Registro operazioni" not in client.get(f"/assemblee/{assemblea.pk}/").text
        client.force_login(rdz)
        assert client.get(url).status_code == 200
        assert "Registro operazioni" in client.get(f"/assemblee/{assemblea.pk}/").text

    def test_comitato_elettorale_escluso(self, client, assemblea):
        operatore = _persona("operatore@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        client.force_login(operatore)
        assert client.get(f"/assemblee/{assemblea.pk}/registro/").status_code == 403


class TestVoci:
    def test_chi_ha_aperto_la_seduta(self, assemblea, segreteria):
        operatore = _persona("operatore@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        seduta = assemblea.sedute.get()
        with set_actor(operatore):
            sedute.apri_seduta(seduta, operatore)
        apertura = next(
            v
            for v in registro.voci(assemblea, "seduta")
            if any(m.campo == "aperta il" for m in v.modifiche)
        )
        assert apertura.autore == str(operatore)
        assert apertura.azione == "Modifica"
        assert apertura.tipo == "Seduta"

    def test_solo_le_voci_dell_assemblea(self, assemblea, segreteria):
        altra = _assemblea(segreteria, 2028)
        oggetti = {v.oggetto for v in registro.voci(assemblea)}
        assert str(assemblea) in oggetti
        assert str(altra) not in oggetti

    def test_oggetti_eliminati_restano_nel_registro(self, assemblea, segreteria):
        """Una verifica annullata si elimina con le sue presenze: le voci si
        riconducono all'assemblea anche se appello e presenza non esistono più."""
        seduta = assemblea.sedute.get()
        sedute.apri_seduta(seduta, segreteria)
        avente = assemblea.aventi_diritto.get()
        sedute.registra_presenza(seduta, avente, segreteria)
        sedute.dichiara_costituita(seduta, segreteria)
        sedute.apri_verifica(seduta, RichiedenteVerifica.PRESIDENZA, segreteria)
        sedute.registra_presenza(seduta, avente, segreteria)
        sedute.annulla_verifica(seduta, segreteria)
        voci = registro.voci(assemblea)
        eliminate = {v.tipo for v in voci if v.azione == "Eliminazione"}
        assert eliminate == {"Appello", "Presenza"}

    def test_filtro_per_tipo(self, assemblea):
        assert {v.tipo for v in registro.voci(assemblea, "seduta")} == {"Seduta"}

    def test_valori_leggibili(self, assemblea):
        creazione = next(
            v for v in registro.voci(assemblea, "assemblea") if v.azione == "Creazione"
        )
        valori = {m.campo: m.dopo for m in creazione.modifiche}
        assert valori["tipo"] == "Autunnale"
        assert valori["Assemblea di prova"] == "no"

    def test_date_nel_fuso_locale(self, assemblea, segreteria):
        seduta = assemblea.sedute.get()
        sedute.apri_seduta(seduta, segreteria)
        seduta.refresh_from_db()
        apertura = next(
            m
            for v in registro.voci(assemblea, "seduta")
            for m in v.modifiche
            if m.campo == "aperta il"
        )
        assert apertura.dopo == f"{timezone.localtime(seduta.aperta_il):%d/%m/%Y %H:%M:%S}"
        creazione = next(v for v in registro.voci(assemblea, "seduta") if v.azione == "Creazione")
        assert {m.campo: m.dopo for m in creazione.modifiche}["data"] == "22/11/2026"
