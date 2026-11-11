"""Riallineamento dell'elenco con l'anagrafica e «Ripristina» che riallinea."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco
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
def avellino() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def ariano() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="ARIANO 1")


@pytest.fixture
def assemblea(segreteria, avellino) -> Assemblea:
    for codice in ("100", "101", "102"):
        capo = Capo.objects.create(
            codice_socio=codice, nome="Nome", cognome=f"C{codice}", email=f"c{codice}@example.it"
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=avellino)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _avente(assemblea, codice):
    return assemblea.aventi_diritto.get(codice_socio=codice)


def test_niente_da_fare_se_gia_allineato(assemblea):
    assert elenco.anteprima_riallinea(assemblea) == []


def test_aggiorna_dati_senza_toccare_le_correzioni(assemblea, segreteria):
    Capo.objects.filter(pk__in=["100", "101"]).update(sesso="F", cognome="Nuovo")
    Capo.objects.filter(pk="101").update(email="nuova101@example.it")
    Capo.objects.filter(pk="100").update(email="nuova100@example.it")
    corretto = _avente(assemblea, "100")
    elenco.aggiorna_email(corretto, "mia@example.it", segreteria)
    elenco.aggiorna_sesso(corretto, "M", segreteria)

    righe = {
        r.avente.codice_socio: {m.campo for m in r.modifiche}
        for r in elenco.anteprima_riallinea(assemblea)
    }
    assert righe == {"100": {"cognome"}, "101": {"cognome", "sesso", "email"}}
    assert elenco.applica_riallinea(assemblea, segreteria) == 2
    assert elenco.applica_riallinea(assemblea, segreteria) == 0  # idempotente

    corretto.refresh_from_db()
    altro = _avente(assemblea, "101")
    assert (
        corretto.cognome == "Nuovo" and corretto.email == "mia@example.it" and corretto.sesso == "M"
    )
    assert altro.email == "nuova101@example.it" and altro.sesso == "F"
    # L'anagrafica non si scrive.
    assert Capo.objects.get(pk="100").email == "nuova100@example.it"


def test_un_valore_vuoto_in_anagrafica_non_cancella(assemblea, segreteria):
    elenco.aggiorna_email(_avente(assemblea, "102"), "c102@example.it", segreteria)
    Capo.objects.filter(pk="101").update(email="", nome="")
    assert elenco.anteprima_riallinea(assemblea) == []


def test_gruppo_del_censimento_e_trasferimenti_a_mano(assemblea, segreteria, avellino, ariano):
    CensimentoCapo.objects.filter(capo_id__in=["100", "101"]).update(gruppo=ariano)
    trasferito = _avente(assemblea, "101")
    terzo = Gruppo.objects.create(codice="E0135", nome="MONTELLA 1")
    elenco.trasferisci(trasferito, terzo, segreteria)

    elenco.applica_riallinea(assemblea, segreteria)
    fermo = _avente(assemblea, "100")
    trasferito.refresh_from_db()
    assert fermo.gruppo == ariano and fermo.gruppo_origine == ariano
    # Trasferito a mano: resta dov'è, cambia solo il gruppo del censimento.
    assert trasferito.gruppo == terzo and trasferito.gruppo_origine == ariano


def test_esclusi_senza_codice_e_usciti(assemblea, segreteria, avellino):
    elenco.inserisci(
        assemblea,
        segreteria,
        nome="Senza",
        cognome="Codice",
        gruppo=avellino,
        provenienza=Provenienza.RIENTRO,
    )
    elenco.elimina([_avente(assemblea, "102")], segreteria)
    Capo.objects.filter(pk="102").update(cognome="Cambiato")
    assert elenco.anteprima_riallinea(assemblea) == []


def test_collega_il_capo_comparso_in_anagrafica(assemblea, segreteria, avellino):
    manuale = elenco.inserisci(
        assemblea,
        segreteria,
        nome="Nuovo",
        cognome="Arrivo",
        gruppo=avellino,
        provenienza=Provenienza.RIENTRO,
        codice_socio="300",
    )
    assert manuale.capo is None
    Capo.objects.create(codice_socio="300", nome="Nuovo", cognome="Arrivo", sesso="M")
    elenco.applica_riallinea(assemblea, segreteria)
    manuale.refresh_from_db()
    assert manuale.capo_id == "300" and manuale.sesso == "M"


def test_ripristina_riallinea(assemblea, segreteria):
    avente = _avente(assemblea, "102")
    elenco.elimina([avente], segreteria)
    Capo.objects.filter(pk="102").update(cognome="Aggiornato", sesso="F")
    avente.refresh_from_db()
    modifiche = elenco.ripristina(avente, segreteria)
    avente.refresh_from_db()
    assert {m.campo for m in modifiche} == {"cognome", "sesso"}
    assert not avente.eliminato and avente.cognome == "Aggiornato"


def test_solo_gestori_e_non_a_conclusa(assemblea, segreteria):
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    with pytest.raises(PermissionDenied):
        elenco.applica_riallinea(assemblea, capo)
    assemblea.conclusa_il = timezone.now()
    assemblea.save()
    with pytest.raises(ValidationError):
        elenco.applica_riallinea(assemblea, segreteria)


def test_dalla_pagina(client, assemblea, segreteria):
    Capo.objects.filter(pk="100").update(sesso="M")
    client.force_login(segreteria)
    pagina = client.get(f"/assemblee/{assemblea.pk}/elenco/riallinea/")
    assert pagina.status_code == 200 and "Sesso" in pagina.content.decode()
    client.post(f"/assemblee/{assemblea.pk}/elenco/riallinea/")
    assert _avente(assemblea, "100").sesso == "M"
