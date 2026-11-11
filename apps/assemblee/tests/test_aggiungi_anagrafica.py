"""Assemblea con elenco vuoto e capi aggiunti dall'anagrafica (singoli, per
gruppo, tutti)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco
from apps.assemblee.models import Assemblea, Seduta, TipoAssemblea
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
def gruppi() -> tuple[Gruppo, Gruppo]:
    avellino = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    ariano = Gruppo.objects.create(codice="E0134", nome="ARIANO 1")
    for codice, gruppo, anno in [
        ("100", avellino, 2026),
        ("101", avellino, 2026),
        ("200", ariano, 2026),
        # Ariano ha già i dati dell'anno in corso: vale quell'anno, non il 2026.
        ("201", ariano, 2027),
    ]:
        capo, _ = Capo.objects.get_or_create(
            codice_socio=codice, defaults={"nome": "Nome", "cognome": f"Capo{codice}", "sesso": "F"}
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=anno, gruppo=gruppo)
    return avellino, ariano


@pytest.fixture
def vuota(gruppi) -> Assemblea:
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    return assemblea


def test_censiti_proposti_con_l_anno_del_gruppo(vuota):
    codici = set(elenco.censiti_aggiungibili(vuota).values_list("capo_id", flat=True))
    assert codici == {"100", "101", "201"}


def test_aggiungi_un_capo(vuota, segreteria):
    avente = elenco.aggiungi_da_anagrafica(vuota, "201", segreteria)
    assert avente.anno_censimento == 2027 and avente.sesso == "F" and avente.vota_in_app
    assert avente.gruppo.codice == "E0134"
    with pytest.raises(ValidationError):
        elenco.aggiungi_da_anagrafica(vuota, "201", segreteria)
    with pytest.raises(ValidationError):
        elenco.aggiungi_da_anagrafica(vuota, "200", segreteria)  # anno non usato
    assert set(elenco.censiti_aggiungibili(vuota).values_list("capo_id", flat=True)) == {
        "100",
        "101",
    }


def test_un_uscito_si_ripristina_non_si_reimporta(vuota, segreteria):
    avente = elenco.aggiungi_da_anagrafica(vuota, "100", segreteria)
    elenco.elimina([avente], segreteria)
    with pytest.raises(ValidationError, match="ripristinalo"):
        elenco.aggiungi_da_anagrafica(vuota, "100", segreteria)
    assert elenco.importa_elenco(vuota, segreteria) == 2  # 101 e 201, non 100


def test_gruppo_intero_e_poi_tutti(vuota, segreteria, gruppi):
    avellino, _ = gruppi
    assert elenco.importa_elenco(vuota, segreteria, gruppi=[avellino]) == 2
    assert elenco.importa_elenco(vuota, segreteria) == 1
    assert elenco.importa_elenco(vuota, segreteria) == 0


def test_solo_gestori(vuota):
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    with pytest.raises(PermissionDenied):
        elenco.aggiungi_da_anagrafica(vuota, "100", capo)


def test_creazione_con_elenco_vuoto(client, segreteria, gruppi):
    client.force_login(segreteria)
    risposta = client.post(
        "/assemblee/nuova/",
        {
            "tipo": TipoAssemblea.AUTUNNALE,
            "anno_scout": 2027,
            "sessione": "ORDINARIA",
            "data_convocazione": "2026-11-22",
            "elenco_iniziale": "VUOTA",
        },
    )
    assemblea = Assemblea.objects.get()
    assert risposta.url == f"/assemblee/{assemblea.pk}/elenco/aggiungi/"
    assert not assemblea.aventi_diritto.exists()


def test_pagina_e_ricerca(client, vuota, segreteria, gruppi):
    client.force_login(segreteria)
    url = f"/assemblee/{vuota.pk}/elenco/aggiungi/"
    assert client.get(url).status_code == 200
    risultati = client.get(url + "cerca/", {"q": "capo"}).json()["risultati"]
    assert [r["codice_socio"] for r in risultati] == ["100", "101", "201"]
    assert set(risultati[0]) == {"codice_socio", "nome", "cognome", "gruppo"}

    client.post(url, {"azione": "capo", "codice_socio": "100"})
    client.post(url, {"azione": "gruppo", "gruppo": gruppi[1].pk})
    assert set(vuota.aventi_diritto.values_list("codice_socio", flat=True)) == {"100", "201"}
    client.post(url, {"azione": "tutti"})
    assert vuota.aventi_diritto.count() == 3


def test_ricerca_solo_gestori(client, vuota):
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    client.force_login(capo)
    assert client.get(f"/assemblee/{vuota.pk}/elenco/aggiungi/cerca/?q=capo").status_code == 403
