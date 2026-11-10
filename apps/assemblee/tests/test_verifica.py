"""Verifica del quorum durante i lavori (regolamento art. 4 c.5-6)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import ValidationError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, sedute
from apps.assemblee.models import (
    Appello,
    Assemblea,
    RichiedenteVerifica,
    Seduta,
    TipoAppello,
    TipoAssemblea,
)
from apps.assemblee.quorum import appello_effettivo, stato_quorum, verifica_in_corso
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
def seduta(segreteria) -> Seduta:
    """Dieci aventi diritto (quorum 6), sette presenti all'ingresso, costituita."""
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for i in range(10):
        capo = Capo.objects.create(codice_socio=str(i), nome="Nome", cognome=f"C{i}")
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    seduta = Seduta.objects.create(
        assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22)
    )
    elenco.importa_elenco(assemblea, segreteria)
    sedute.apri_seduta(seduta, segreteria)
    _presenti(seduta, segreteria, range(7))
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


def _presenti(seduta, utente, codici):
    for codice in codici:
        avente = seduta.assemblea.aventi_diritto.get(codice_socio=str(codice))
        sedute.registra_presenza(seduta, avente, utente)


def _apri(seduta, utente):
    return sedute.apri_verifica(seduta, RichiedenteVerifica.CAPI, utente)


def test_durante_la_verifica_valgono_i_presenti_precedenti(seduta, segreteria):
    verifica = _apri(seduta, segreteria)
    assert verifica.tipo == TipoAppello.VERIFICA and verifica.numero == 2
    _presenti(seduta, segreteria, range(4))
    assert stato_quorum(seduta).presenti == 7
    assert stato_quorum(seduta, verifica).presenti == 4


def test_chiusura_con_quorum_mancante(seduta, segreteria):
    _apri(seduta, segreteria)
    _presenti(seduta, segreteria, range(4))
    verifica = sedute.chiudi_verifica(seduta, segreteria)
    assert (verifica.presenti_rilevati, verifica.soglia, verifica.quorum_raggiunto) == (
        4,
        6,
        False,
    )
    assert appello_effettivo(seduta) == verifica
    assert stato_quorum(seduta).presenti == 4
    assert verifica_in_corso(seduta) is None


def test_chiusura_con_quorum_confermato(seduta, segreteria):
    _apri(seduta, segreteria)
    _presenti(seduta, segreteria, range(8))
    assert sedute.chiudi_verifica(seduta, segreteria).quorum_raggiunto


def test_annulla_torna_ai_presenti_dell_ingresso(seduta, segreteria):
    _apri(seduta, segreteria)
    _presenti(seduta, segreteria, range(2))
    sedute.annulla_verifica(seduta, segreteria)
    assert appello_effettivo(seduta).tipo == TipoAppello.INGRESSO
    assert stato_quorum(seduta).presenti == 7
    assert Appello.objects.filter(tipo=TipoAppello.VERIFICA).count() == 0


def test_una_verifica_alla_volta_e_solo_durante_i_lavori(seduta, segreteria):
    _apri(seduta, segreteria)
    with pytest.raises(ValidationError):
        _apri(seduta, segreteria)
    sedute.annulla_verifica(seduta, segreteria)
    with pytest.raises(ValidationError):
        sedute.apri_verifica(seduta, "QUALCUNO", segreteria)

    Seduta.objects.filter(pk=seduta.pk).update(costituita=None)
    seduta.refresh_from_db()
    with pytest.raises(ValidationError):
        _apri(seduta, segreteria)


def test_pagina_presenze_filtra_chi_va_rispuntato(client, seduta, segreteria):
    _apri(seduta, segreteria)
    _presenti(seduta, segreteria, [0, 1])
    client.force_login(segreteria)
    response = client.get(
        f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/presenze/", {"precedenti": "1"}
    )
    assert sorted(r.codice_socio for r in response.context["righe"]) == [
        "2",
        "3",
        "4",
        "5",
        "6",
    ]


def test_chiusura_dalla_pagina_richiede_conferma(client, seduta, segreteria):
    _apri(seduta, segreteria)
    client.force_login(segreteria)
    url = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/azione/"
    client.post(url, {"azione": "chiudi_verifica"})
    assert verifica_in_corso(seduta) is not None
    client.post(url, {"azione": "chiudi_verifica", "conferma": "1"})
    assert verifica_in_corso(seduta) is None
