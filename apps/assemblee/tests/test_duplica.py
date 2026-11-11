"""Duplicazione di un'assemblea (duplica.py): si copia l'elenco, non il voto."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo, FunzioneIncarico
from apps.assemblee import comitato, duplica, elenco, odg, sedute, votazioni
from apps.assemblee.models import (
    Assemblea,
    OperatoreVoto,
    Provenienza,
    Seduta,
    SistemaVoto,
    TipoAssemblea,
    TipoVotazione,
    Votazione,
)
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
def origine(segreteria, gruppo) -> Assemblea:
    """Assemblea già svolta: elenco ritoccato a mano, comitato, odg, una seduta
    costituita con presenze e una votazione."""
    for i in range(4):
        capo = Capo.objects.create(
            codice_socio=f"10{i}", nome="Nome", cognome=f"Capo{i}", email=f"capo{i}@example.it"
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(
        tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027, sistema_voto=SistemaVoto.CATELLO
    )
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    elenco.inserisci(
        assemblea,
        segreteria,
        nome="Nuovo",
        cognome="Arrivato",
        gruppo=gruppo,
        provenienza=Provenienza.NUOVO_INGRESSO,
        email="nuovo@example.it",
        incarichi=[
            {"funzione": FunzioneIncarico.CAPO_UNITA, "branca": "", "nome_unita": "Reparto"}
        ],
    )
    aventi = {a.codice_socio: a for a in assemblea.aventi_diritto.all()}
    elenco.elimina([aventi["103"]], segreteria)
    elenco.aggiorna_email(aventi["101"], "corretta@example.it", segreteria)
    elenco.passa_a_carta(aventi["102"], segreteria)
    comitato.aggiungi(assemblea, aventi["100"], segreteria)
    comitato.aggiungi(assemblea, aventi["101"], segreteria, accesso=False)
    punto = odg.aggiungi_punto(assemblea, segreteria, "Bilancio")
    odg.modifica_punto(punto, segreteria, titolo="Bilancio", testo="Discussione del giorno.")

    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    for avente in assemblea.aventi_diritto.nell_elenco():
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    votazioni.apri_votazione(seduta, segreteria, tipo=TipoVotazione.BILANCIO, oggetto="Bilancio")
    return assemblea


def _nuova() -> Assemblea:
    nuova = Assemblea.objects.create(
        tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027, sistema_voto=SistemaVoto.CATELLO
    )
    Seduta.objects.create(assemblea=nuova, convocazione=1, data=datetime.date(2026, 12, 13))
    return nuova


def test_copia_l_elenco_come_e(origine, segreteria):
    nuova = _nuova()
    assert duplica.copia_in(origine, nuova, segreteria) == 5

    copiati = {a.cognome: a for a in nuova.aventi_diritto.all()}
    assert set(copiati) == {"Capo0", "Capo1", "Capo2", "Capo3", "Arrivato"}
    assert copiati["Capo3"].eliminato and copiati["Capo3"].uscita
    assert copiati["Capo1"].email == "corretta@example.it"
    assert list(copiati["Arrivato"].incarichi.values_list("nome_unita", flat=True)) == ["Reparto"]
    # Il passaggio a carta vale solo per il giorno dell'assemblea.
    assert not copiati["Capo2"].passato_a_carta and copiati["Capo2"].vota_in_app
    # L'origine resta com'era.
    assert origine.aventi_diritto.count() == 5


def test_non_copia_il_voto(origine, segreteria):
    nuova = _nuova()
    duplica.copia_in(origine, nuova, segreteria)
    assert not Votazione.objects.filter(seduta__assemblea=nuova).exists()
    assert nuova.sedute.count() == 1 and nuova.sedute.get().aperta_il is None
    assert not nuova.aventi_diritto.filter(presenze__isnull=False).exists()
    punto = nuova.punti_odg.get()
    assert punto.titolo == "Bilancio" and punto.testo == ""


def test_copia_il_comitato_con_gli_stessi_account(origine, segreteria):
    nuova = _nuova()
    duplica.copia_in(origine, nuova, segreteria)
    vecchi = {c.nome_completo: c.utente_id for c in origine.operatori.all()}
    nuovi = {c.nome_completo: c.utente_id for c in nuova.operatori.all()}
    assert nuovi == vecchi
    assert all(c.avente.assemblea_id == nuova.pk for c in nuova.operatori.all())


def test_solo_i_gestori(origine):
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    with pytest.raises(PermissionDenied):
        duplica.copia_in(origine, _nuova(), capo)


def test_dalla_pagina(client, origine, segreteria):
    client.force_login(segreteria)
    pagina = client.get(f"/assemblee/{origine.pk}/duplica/")
    assert pagina.status_code == 200
    assert pagina.context["form"].initial["sistema_voto"] == SistemaVoto.CATELLO

    risposta = client.post(
        f"/assemblee/{origine.pk}/duplica/",
        {
            "tipo": TipoAssemblea.AUTUNNALE,
            "anno_scout": 2027,
            "sessione": origine.sessione,
            "sistema_voto": SistemaVoto.CATELLO,
            "modalita_voto": origine.modalita_voto,
            "data_convocazione": "2026-12-13",
        },
    )
    nuova = Assemblea.objects.exclude(pk=origine.pk).get()
    assert risposta.status_code == 302
    assert nuova.creata_da == segreteria
    assert nuova.aventi_diritto.count() == 5
    assert OperatoreVoto.objects.filter(assemblea=nuova).count() == 2


def test_pagina_solo_per_i_gestori(client, origine):
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    client.force_login(capo)
    assert client.get(f"/assemblee/{origine.pk}/duplica/").status_code == 403
