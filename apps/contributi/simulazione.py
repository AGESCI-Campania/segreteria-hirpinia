"""Simulazione del calcolo (D-16, §7 passo 4): la segreteria può eseguire il
calcolo a vuoto quante volte vuole prima di chiudere, senza scrivere gli
importi definitivi. Ogni esecuzione sostituisce la simulazione precedente
della stessa campagna: nessuno storico dei tentativi, solo l'ultimo risultato."""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import Utente

from .calcolo import RisultatoCalcolo, calcola_importi
from .campagne import verifica_ruolo_gestione_campagna
from .models import Campagna, ContributoPartecipazione


@transaction.atomic
def simula_calcolo(*, utente: Utente, campagna: Campagna) -> RisultatoCalcolo:
    verifica_ruolo_gestione_campagna(utente)
    risultato = calcola_importi(campagna)
    ContributoPartecipazione.objects.filter(
        partecipazione__campagna=campagna, is_simulazione=True
    ).delete()
    ContributoPartecipazione.objects.bulk_create(
        ContributoPartecipazione(
            partecipazione_id=partecipazione_id, importo=importo, is_simulazione=True
        )
        for partecipazione_id, importo in risultato.importi.items()
    )
    return risultato
