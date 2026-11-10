"""Ballottaggio in app con il voto di Catello (V5)."""

import pytest
from django.core.exceptions import ValidationError

from apps.assemblee import sedute, votazioni
from apps.assemblee.models import CanaleVoto, SistemaVoto, TipoVotazione
from apps.voto import codici, scrutinio, urna

from .conftest import avente

pytestmark = pytest.mark.django_db


@pytest.fixture
def ballottaggio(seduta, assemblea, segreteria):
    for cognome in ("Rossi", "Bianchi", "Verdi", "Neri"):
        sedute.registra_presenza(seduta, avente(assemblea, cognome), segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    elezione = votazioni.apri_votazione(
        seduta,
        segreteria,
        tipo=TipoVotazione.ELEZIONE,
        oggetto="Elezione",
        incarico="Capo Guida",
        candidati=["Anna", "Bruno", "Carla"],
    )
    voti = {
        c.pk: {"voti_carta": n}
        for c, n in zip(elezione.candidati.order_by("nome"), (1, 1, 0), strict=True)
    }
    votazioni.registra_risultati(
        elezione, segreteria, per_canale={CanaleVoto.CARTA: {}}, voti_candidati=voti
    )
    return votazioni.apri_ballottaggio(elezione, segreteria)


def _codice(seduta, assemblea, cognome, utente):
    codici.emetti(seduta, avente(assemblea, cognome), utente)
    return codici.codice_attivo(seduta, avente(assemblea, cognome))


def test_canali_app_e_carta_solo_con_catello(ballottaggio, assemblea):
    assert votazioni.canali(ballottaggio) == [CanaleVoto.APP, CanaleVoto.CARTA]
    assemblea.sistema_voto = SistemaVoto.NAZIONALE
    assemblea.save()
    ballottaggio.seduta.assemblea.refresh_from_db()
    assert votazioni.canali(ballottaggio) == [CanaleVoto.CARTA]


def test_ballottaggio_in_app_fino_al_risultato(ballottaggio, seduta, assemblea, segreteria):
    scrutinio.apri_urna(ballottaggio, segreteria)
    anna = ballottaggio.candidati.get(nome="Anna").pk
    for cognome in ("Rossi", "Bianchi", "Verdi"):
        codice = _codice(seduta, assemblea, cognome, segreteria)
        urna.vota(codice.pk, ballottaggio, [urna.Scelte(candidati=(anna,))])
    scrutinio.chiudi_urna(ballottaggio, segreteria)
    esito = votazioni.registra_risultati(ballottaggio, segreteria, per_canale={})
    assert [c.nome for c in esito.eletti] == ["Anna"]


def test_nel_ballottaggio_niente_nomi_scritti(ballottaggio, seduta, assemblea, segreteria):
    scrutinio.apri_urna(ballottaggio, segreteria)
    codice = _codice(seduta, assemblea, "Rossi", segreteria)
    with pytest.raises(ValidationError):
        urna.vota(codice.pk, ballottaggio, [urna.Scelte(liberi=("Carla",))])
