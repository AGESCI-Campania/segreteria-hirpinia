"""Fixture comuni ai test del voto elettronico: un'assemblea con il voto di
Catello, una seduta aperta e qualche avente diritto."""

import datetime

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, sedute
from apps.assemblee.models import (
    Assemblea,
    OperatoreVoto,
    Provenienza,
    Seduta,
    SistemaVoto,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo


def persona(email: str, ruolo: str | None = None) -> Utente:
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
    return persona("segreteria@campania.agesci.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def avellino() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def assemblea(segreteria, avellino) -> Assemblea:
    dati = [
        ("100001", "Mario", "Rossi", "mario@example.it"),
        ("100002", "Anna", "Bianchi", ""),
        ("100003", "Luca", "Verdi", "luca@example.it"),
        ("100004", "Pia", "Neri", "pia@example.it"),
    ]
    for codice, nome, cognome, email in dati:
        capo = Capo.objects.create(codice_socio=codice, nome=nome, cognome=cognome, email=email)
        CensimentoCapo.objects.create(capo=capo, anno_scout=2027, gruppo=avellino)
    assemblea = Assemblea.objects.create(
        tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027, sistema_voto=SistemaVoto.CATELLO
    )
    elenco.importa_elenco(assemblea, segreteria)
    # Inserito a mano senza codice socio: con il voto di Catello vota in app.
    elenco.inserisci(
        assemblea,
        segreteria,
        nome="Sara",
        cognome="Gialli",
        gruppo=avellino,
        provenienza=Provenienza.NUOVO_INGRESSO,
    )
    return assemblea


@pytest.fixture
def seduta(assemblea, segreteria) -> Seduta:
    seduta = Seduta.objects.create(
        assemblea=assemblea, convocazione=1, data=datetime.date(2027, 4, 10)
    )
    sedute.apri_seduta(seduta, segreteria)
    return seduta


@pytest.fixture
def operatore(assemblea) -> Utente:
    utente = persona("operatore@example.it")
    OperatoreVoto.objects.create(assemblea=assemblea, utente=utente)
    return utente


def avente(assemblea, cognome):
    return assemblea.aventi_diritto.get(cognome=cognome)
