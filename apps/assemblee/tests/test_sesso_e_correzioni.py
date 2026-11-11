"""Sesso nell'elenco e correzioni fatte nel modulo (email, sesso)."""

import datetime
import importlib

import pytest
from allauth.mfa.models import Authenticator
from django.apps import apps as registro

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, email_aventi
from apps.assemblee.models import Assemblea, Provenienza, Seduta, TipoAssemblea
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
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def assemblea(segreteria, gruppo) -> Assemblea:
    for codice, sesso in [("100", "M"), ("101", "F"), ("102", ""), ("103", "X")]:
        capo = Capo.objects.create(
            codice_socio=codice,
            nome="Nome",
            cognome=f"C{codice}",
            sesso=sesso,
            email=f"c{codice}@example.it",
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _sessi(assemblea) -> dict[str, str]:
    return dict(assemblea.aventi_diritto.values_list("codice_socio", "sesso"))


def test_import_prende_il_sesso_senza_normalizzare(assemblea):
    # «X» non è un valore atteso: resta non noto, non si indovina.
    assert _sessi(assemblea) == {"100": "M", "101": "F", "102": "", "103": ""}
    assert not assemblea.aventi_diritto.filter(email_corretta=True).exists()


def test_correzioni_nel_modulo_sono_marcate(assemblea, segreteria):
    avente = assemblea.aventi_diritto.get(codice_socio="102")
    assert elenco.aggiorna_sesso(avente, "F", segreteria)
    assert not elenco.aggiorna_sesso(avente, "F", segreteria)
    assert elenco.aggiorna_email(avente, "nuova@example.it", segreteria)
    avente.refresh_from_db()
    assert avente.sesso == "F" and avente.sesso_corretto
    assert avente.email_corretta
    # L'anagrafica non cambia.
    assert Capo.objects.get(pk="102").sesso == ""


def test_sesso_non_valido(assemblea, segreteria):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        elenco.aggiorna_sesso(assemblea.aventi_diritto.first(), "X", segreteria)


def test_inserimento_a_mano(assemblea, segreteria, gruppo):
    capo = Capo.objects.create(codice_socio="200", nome="N", cognome="Nuovo", sesso="M")
    dal_capo = elenco.inserisci(
        assemblea,
        segreteria,
        nome="N",
        cognome="Nuovo",
        gruppo=gruppo,
        provenienza=Provenienza.RIENTRO,
        codice_socio=capo.pk,
    )
    assert dal_capo.sesso == "M" and not dal_capo.sesso_corretto
    a_mano = elenco.inserisci(
        assemblea,
        segreteria,
        nome="A",
        cognome="Mano",
        gruppo=gruppo,
        provenienza=Provenienza.RIENTRO,
        sesso="F",
        email="a@example.it",
    )
    assert a_mano.sesso == "F" and a_mano.sesso_corretto and a_mano.email_corretta


def test_import_excel_marca_l_email_corretta(assemblea, segreteria, gruppo):
    avente = assemblea.aventi_diritto.get(codice_socio="100")
    contenuto = email_aventi.genera_excel_gruppo(assemblea, gruppo, segreteria)
    import io

    from openpyxl import load_workbook

    libro = load_workbook(io.BytesIO(contenuto))
    foglio = libro.active
    for riga in foglio.iter_rows(min_row=2):
        if riga[0].value == avente.pk:
            riga[4].value = "dal-capogruppo@example.it"
    uscita = io.BytesIO()
    libro.save(uscita)
    email_aventi.applica_import(assemblea, uscita.getvalue(), "f.xlsx", segreteria)
    avente.refresh_from_db()
    assert avente.email == "dal-capogruppo@example.it" and avente.email_corretta


def test_migrazione_riempie_sesso_e_riconosce_le_email_corrette(assemblea):
    assemblea.aventi_diritto.update(sesso="", email_corretta=False)
    cambiata = assemblea.aventi_diritto.get(codice_socio="101")
    cambiata.email = "diversa@example.it"
    cambiata.save()
    migrazione = importlib.import_module("apps.assemblee.migrations.0014_sesso_e_correzioni_avente")
    migrazione.da_anagrafica(registro, None)
    assert _sessi(assemblea) == {"100": "M", "101": "F", "102": "", "103": ""}
    assert list(
        assemblea.aventi_diritto.filter(email_corretta=True).values_list("codice_socio", flat=True)
    ) == ["101"]


def test_pagina_dati(client, assemblea, segreteria):
    avente = assemblea.aventi_diritto.get(codice_socio="102")
    client.force_login(segreteria)
    url = f"/assemblee/{assemblea.pk}/elenco/{avente.pk}/email/"
    assert client.get(url).status_code == 200
    client.post(url, {"email": avente.email, "sesso": "M"})
    avente.refresh_from_db()
    assert avente.sesso == "M" and avente.sesso_corretto and not avente.email_corretta


def test_elenco_evidenzia_e_filtra_i_dati_mancanti(client, assemblea, segreteria):
    elenco.aggiorna_email(assemblea.aventi_diritto.get(codice_socio="101"), "", segreteria)
    client.force_login(segreteria)
    url = f"/assemblee/{assemblea.pk}/elenco/"
    risposta = client.get(url)
    assert risposta.context["totale_senza_sesso"] == 2
    assert risposta.context["totale_senza_email"] == 1
    assert "Manca" in risposta.content.decode()
    filtrate = client.get(url, {"incompleti": "1"}).context["righe"]
    assert sorted(r.codice_socio for r in filtrate) == ["101", "102", "103"]
