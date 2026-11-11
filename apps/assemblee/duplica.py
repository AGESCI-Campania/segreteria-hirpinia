"""Duplicazione di un'assemblea (D-70): una nuova assemblea, con la sua prima
convocazione, che riparte dall'elenco degli aventi diritto di un'altra.

Si copiano l'elenco così com'è (eliminazioni, trasferimenti, email, qualifiche
e incarichi dichiarati compresi), il comitato elettorale, presidenza, segretario,
comitato mozioni e scrutatori e i titoli dei punti
all'ordine del giorno. Non si copiano sedute, presenze, deleghe, votazioni,
codici di voto, seggi, verbali, né i passaggi a carta, che valgono solo per
il giorno dell'assemblea: il voto in app si ricalcola con la regola di
sempre. L'anagrafica non si legge né si scrive: per riallineare l'elenco ai
censiti resta «Aggiorna gruppo»."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import Utente

from . import elenco
from .models import (
    Assemblea,
    AventeDiritto,
    IncaricoAssemblea,
    IncaricoDichiarato,
    OperatoreVoto,
    PuntoOdG,
)
from .permessi import puo_gestire_assemblee

# Campi dell'avente che descrivono il capo nell'elenco, e quindi si copiano.
_CAMPI_AVENTE = [
    "capo_id",
    "codice_socio",
    "nome",
    "cognome",
    "email",
    "email_corretta",
    "sesso",
    "sesso_corretto",
    "gruppo_id",
    "gruppo_origine_id",
    "origine",
    "provenienza",
    "anno_censimento",
    "uscita",
    "ae_zona",
    "rdz",
    "comitato",
    "eliminato_il",
    "eliminato_da_id",
]


@transaction.atomic
def copia_in(origine: Assemblea, nuova: Assemblea, utente: Utente) -> int:
    """Copia in `nuova` (appena creata, vuota) il contenuto di `origine`.
    Restituisce quanti aventi diritto sono stati copiati."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    assert not nuova.aventi_diritto.exists(), "La copia va fatta in un'assemblea vuota."

    corrispondenze: dict[int, AventeDiritto] = {}
    for vecchio in origine.aventi_diritto.prefetch_related("incarichi"):
        nuovo = AventeDiritto(
            assemblea=nuova,
            creato_da=utente,
            **{campo: getattr(vecchio, campo) for campo in _CAMPI_AVENTE},
        )
        nuovo.vota_in_app = elenco.calcola_vota_in_app(nuovo)
        nuovo.save()
        corrispondenze[vecchio.pk] = nuovo
        IncaricoDichiarato.objects.bulk_create(
            IncaricoDichiarato(
                avente=nuovo,
                funzione=incarico.funzione,
                branca=incarico.branca,
                nome_unita=incarico.nome_unita,
            )
            for incarico in vecchio.incarichi.all()
        )

    for componente in origine.operatori.all():
        avente = corrispondenze.get(componente.avente_id) if componente.avente_id else None
        if avente is not None and avente.eliminato_il is not None:
            continue
        if avente is None and componente.utente_id is None:
            continue
        OperatoreVoto.objects.create(
            assemblea=nuova, avente=avente, utente_id=componente.utente_id, nominato_da=utente
        )

    for incarico in origine.incarichi.all():
        avente = corrispondenze.get(incarico.avente_id)
        if avente is not None and avente.eliminato_il is None:
            IncaricoAssemblea.objects.create(
                assemblea=nuova,
                ruolo=incarico.ruolo,
                avente=avente,
                utente_id=incarico.utente_id,
                nominato_da=utente,
            )

    PuntoOdG.objects.bulk_create(
        PuntoOdG(assemblea=nuova, ordine=punto.ordine, titolo=punto.titolo)
        for punto in origine.punti_odg.all()
    )
    return len(corrispondenze)
