"""Riepilogo di campagna (D-13: "il residuo è mostrato nel riepilogo come
voce esplicita"), mostrato sia a schermo sia nel report PDF (§9, M7). Funzione
pura, nessuna scrittura: riusa `genera_righe_bonifici` (M6) per il residuo,
così un gruppo escluso perché disattivato (M7b) si riflette qui senza
ricalcoli né campi persistiti."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError

from .bonifici import RigaBonifico, genera_righe_bonifici
from .models import Campagna, ContributoPartecipazione
from .visibilita import STATI_CON_VISIBILITA_CROSS_GRUPPO


@dataclass(frozen=True)
class RiepilogoCampagna:
    n: int
    quota_proporzionale: Decimal
    quota_erogata: Decimal
    residuo: Decimal
    righe: list[RigaBonifico]


def calcola_riepilogo(campagna: Campagna) -> RiepilogoCampagna:
    if campagna.stato not in STATI_CON_VISIBILITA_CROSS_GRUPPO:
        raise ValidationError("Il riepilogo è disponibile solo a campagna CHIUSA o LIQUIDATA.")
    # N dalle righe congelate, non dalle Partecipazione correnti: una
    # disattivazione di gruppo post-chiusura (M7b) può respingerne alcune,
    # ma l'importo individuale già congelato non cambia — ricalcolare N da
    # capo produrrebbe una quota_proporzionale diversa da quella realmente
    # usata per gli importi già scritti.
    n = ContributoPartecipazione.objects.filter(
        partecipazione__campagna=campagna, is_simulazione=False
    ).count()
    quota_proporzionale = campagna.budget / n if n else campagna.budget
    # Quota erogata (D-10): il tetto per partecipazione può abbassare
    # l'importo effettivo sotto la quota proporzionale; non riflette
    # l'eventuale ulteriore riduzione per singola partecipazione dovuta a
    # una quota_versata inferiore, che resta visibile riga per riga.
    quota_erogata = min(quota_proporzionale, campagna.tetto_per_partecipazione)
    righe = genera_righe_bonifici(campagna, causale="")
    residuo = campagna.budget - sum((riga.importo for riga in righe), Decimal("0"))
    return RiepilogoCampagna(
        n=n,
        quota_proporzionale=quota_proporzionale,
        quota_erogata=quota_erogata,
        residuo=residuo,
        righe=righe,
    )
