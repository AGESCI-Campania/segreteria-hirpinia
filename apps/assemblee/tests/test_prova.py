"""Assemblee di prova: indicate come tali, eliminabili solo loro."""

import datetime
import io

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.utils import timezone
from pypdf import PdfReader

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import comitato, elenco, file, prova, sedute, votazioni
from apps.assemblee.models import Assemblea, Seduta, TipoAssemblea, TipoVotazione
from apps.organizzazione.models import Gruppo
from apps.voto.models import InterpretazioneNome, Votante

pytestmark = pytest.mark.django_db


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


def _assemblea(segreteria, di_prova: bool) -> Assemblea:
    gruppo, _ = Gruppo.objects.get_or_create(codice="E0133", defaults={"nome": "AVELLINO 1"})
    for i in range(3):
        capo, _ = Capo.objects.get_or_create(
            codice_socio=f"10{i}",
            defaults={"nome": "Nome", "cognome": f"C{i}", "email": f"c{i}@x.it"},
        )
        CensimentoCapo.objects.get_or_create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(
        tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027, di_prova=di_prova
    )
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def test_nome_e_vincolo_mailpit(segreteria):
    assemblea = _assemblea(segreteria, di_prova=True)
    assert str(assemblea) == "Assemblea autunnale 2026/2027 (di prova)"
    with pytest.raises(IntegrityError):
        Assemblea.objects.create(
            tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027, email_solo_mailpit=True
        )


def test_un_assemblea_vera_non_si_elimina(segreteria, client):
    vera = _assemblea(segreteria, di_prova=False)
    with pytest.raises(ValidationError):
        prova.elimina(vera, segreteria)
    client.force_login(segreteria)
    assert client.get(f"/assemblee/{vera.pk}/elimina/").status_code == 403
    assert Assemblea.objects.filter(pk=vera.pk).exists()


def test_eliminazione_con_votazioni_e_comitato(segreteria):
    assemblea = _assemblea(segreteria, di_prova=True)
    aventi = list(assemblea.aventi_diritto.all())
    componente, _ = comitato.aggiungi(assemblea, aventi[0], segreteria)
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    for avente in aventi:
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    votazione = votazioni.apri_votazione(
        seduta,
        segreteria,
        tipo=TipoVotazione.ELEZIONE,
        oggetto="Elezione",
        incarico="Consigliere",
        posti=1,
        candidati=[aventi[1]],
    )
    Votante.objects.create(votazione=votazione, avente=aventi[0])
    InterpretazioneNome.objects.create(
        votazione=votazione, chiave="c2", avente=aventi[2], decisa_il=timezone.now()
    )

    prova.elimina(assemblea, segreteria)
    assert not Assemblea.objects.exists()
    assert not InterpretazioneNome.objects.exists() and not Votante.objects.exists()
    # L'account del comitato è reale: resta.
    assert Utente.objects.filter(pk=componente.utente_id).exists()


def test_solo_gestori(segreteria):
    assemblea = _assemblea(segreteria, di_prova=True)
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    with pytest.raises(PermissionDenied):
        prova.elimina(assemblea, capo)


def test_dalla_pagina_serve_la_conferma(client, segreteria):
    assemblea = _assemblea(segreteria, di_prova=True)
    client.force_login(segreteria)
    url = f"/assemblee/{assemblea.pk}/elimina/"
    assert client.get(url).status_code == 200
    client.post(url)
    assert Assemblea.objects.filter(pk=assemblea.pk).exists()
    client.post(url, {"conferma": "1"})
    assert not Assemblea.objects.filter(pk=assemblea.pk).exists()


def test_creazione_di_prova_e_mailpit_solo_per_le_prove(client, segreteria):
    client.force_login(segreteria)
    dati = {
        "tipo": TipoAssemblea.PRIMAVERILE,
        "anno_scout": 2027,
        "sessione": "ORDINARIA",
        "data_convocazione": "2027-04-10",
        "elenco_iniziale": "VUOTA",
        "email_solo_mailpit": "on",
    }
    client.post("/assemblee/nuova/", dati)
    vera = Assemblea.objects.get()
    assert not vera.di_prova and not vera.email_solo_mailpit
    client.post("/assemblee/nuova/", {**dati, "di_prova": "on"})
    di_prova = Assemblea.objects.get(di_prova=True)
    assert di_prova.email_solo_mailpit


def test_dicitura_nel_pdf(segreteria):
    assemblea = _assemblea(segreteria, di_prova=True)
    contenuto = file.genera_foglio_presenze_pdf(assemblea, segreteria)
    testo = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages)
    assert "DI PROVA" in testo
