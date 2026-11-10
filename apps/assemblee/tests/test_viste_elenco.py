"""Pagine dell'elenco degli aventi diritto (D-70)."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco
from apps.assemblee.models import (
    Assemblea,
    AventeDiritto,
    MotivoUscita,
    OperatoreVoto,
    TipoAssemblea,
)
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


@pytest.fixture
def assemblea(segreteria, avellino, ariano) -> Assemblea:
    for codice, gruppo in (("A1", avellino), ("A2", avellino), ("B1", ariano)):
        capo = Capo.objects.create(codice_socio=codice, nome="Nome", cognome=f"Cognome{codice}")
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def test_creazione_importa_l_elenco(client, segreteria, avellino):
    capo = Capo.objects.create(codice_socio="A1", nome="Mario", cognome="Rossi")
    CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=avellino)
    client.force_login(segreteria)
    client.post(
        "/assemblee/nuova/",
        {
            "tipo": TipoAssemblea.AUTUNNALE,
            "anno_scout": 2027,
            "sessione": "ORDINARIA",
            "data_convocazione": "2026-11-22",
        },
    )
    assemblea = Assemblea.objects.get()
    assert list(assemblea.aventi_diritto.values_list("codice_socio", flat=True)) == ["A1"]


def test_elenco_con_filtro_per_gruppo(client, segreteria, assemblea, ariano):
    client.force_login(segreteria)
    response = client.get(f"/assemblee/{assemblea.pk}/elenco/", {"gruppo": ariano.pk})
    righe = list(response.context["righe"])
    assert [r.codice_socio for r in righe] == ["B1"]
    assert response.context["totale"] == 3


def test_elenco_visibile_all_operatore_senza_azioni_di_gestione(client, assemblea):
    operatore = _persona("operatore@example.it")
    OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
    client.force_login(operatore)
    response = client.get(f"/assemblee/{assemblea.pk}/elenco/")
    assert response.status_code == 200
    assert not response.context["puo_gestire"]
    assert response.context["puo_operare"]


def test_eliminazione_multipla(client, segreteria, assemblea):
    client.force_login(segreteria)
    selezionati = assemblea.aventi_diritto.filter(codice_socio__in=["A1", "A2"])
    client.post(
        f"/assemblee/{assemblea.pk}/elenco/elimina/",
        {"aventi": [a.pk for a in selezionati]},
    )
    assert set(
        assemblea.aventi_diritto.filter(uscita=MotivoUscita.ELIMINATO).values_list(
            "codice_socio", flat=True
        )
    ) == {"A1", "A2"}


def test_eliminazione_vietata_all_operatore(client, assemblea):
    operatore = _persona("operatore@example.it")
    OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
    client.force_login(operatore)
    avente = assemblea.aventi_diritto.first()
    response = client.post(f"/assemblee/{assemblea.pk}/elenco/elimina/", {"aventi": [avente.pk]})
    assert response.status_code == 403


def test_inserimento_con_incarichi(client, segreteria, assemblea, avellino):
    client.force_login(segreteria)
    response = client.post(
        f"/assemblee/{assemblea.pk}/elenco/nuovo/",
        {
            "cognome": "Bianchi",
            "nome": "Anna",
            "gruppo": avellino.pk,
            "provenienza": "PASSAGGIO_CLAN",
            "codice_socio": "",
            "incarichi-TOTAL_FORMS": "3",
            "incarichi-INITIAL_FORMS": "0",
            "incarichi-0-funzione": "CAPO_UNITA",
            "incarichi-0-branca": "LC",
            "incarichi-0-nome_unita": "Branco Seeonee",
            "incarichi-1-funzione": "",
            "incarichi-2-funzione": "",
        },
    )
    assert response.status_code == 302
    avente = assemblea.aventi_diritto.get(cognome="Bianchi")
    assert not avente.vota_in_app
    assert avente.incarichi.get().nome_unita == "Branco Seeonee"


def test_passaggio_a_carta_dall_operatore(client, assemblea):
    operatore = _persona("operatore@example.it")
    OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
    avente = assemblea.aventi_diritto.get(codice_socio="A1")
    client.force_login(operatore)
    client.post(f"/assemblee/{assemblea.pk}/elenco/{avente.pk}/voto-cartaceo/")
    avente.refresh_from_db()
    assert avente.passato_a_carta and not avente.vota_in_app

    response = client.get(f"/assemblee/{assemblea.pk}/elenco/")
    assert list(response.context["da_togliere_dall_app"]) == [avente]


def test_aggiorna_gruppo(client, segreteria, assemblea, avellino):
    capo = Capo.objects.get(codice_socio="A1")
    CensimentoCapo.objects.create(capo=capo, anno_scout=2027, gruppo=avellino)
    client.force_login(segreteria)
    url = f"/assemblee/{assemblea.pk}/elenco/gruppi/{avellino.pk}/aggiorna/"

    anteprima = client.get(url).context["anteprima"]
    assert [a.codice_socio for a in anteprima.escono] == ["A2"]

    client.post(url)
    assert AventeDiritto.objects.get(codice_socio="A2").uscita == MotivoUscita.NON_CENSITO
    assert AventeDiritto.objects.get(codice_socio="A1").anno_censimento == 2027
