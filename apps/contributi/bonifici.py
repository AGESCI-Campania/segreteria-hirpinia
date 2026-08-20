"""Generazione del file bonifici (D-14). Funzione pura, nessuna scrittura:
le view (CSV/XLSX) e qualunque futuro report chiamano solo questa. Calcolato
al momento della generazione sommando le partecipazioni secondo
l'attribuzione **corrente** (D-29) — non un aggregato congelato alla
chiusura: una ri-attribuzione successiva sposta il bonifico al nuovo gruppo
senza bisogno di ricalcoli."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from apps.organizzazione.models import Gruppo

from .models import Campagna, ContributoPartecipazione, StatoCampagna

STATI_CON_IMPORTI_CONGELATI = frozenset({StatoCampagna.CHIUSA, StatoCampagna.LIQUIDATA})


@dataclass(frozen=True)
class RigaBonifico:
    gruppo_codice: str
    denominazione: str
    intestazione_conto: str
    iban: str
    importo: Decimal
    causale: str


def genera_righe_bonifici(campagna: Campagna, *, causale: str) -> list[RigaBonifico]:
    if campagna.stato not in STATI_CON_IMPORTI_CONGELATI:
        raise ValidationError(
            "Gli importi non sono ancora congelati: la campagna deve essere "
            "CHIUSA o LIQUIDATA per generare il file bonifici (D-14)."
        )

    totali = (
        ContributoPartecipazione.objects.filter(
            partecipazione__campagna=campagna, is_simulazione=False
        )
        .values("partecipazione__gruppo")
        .annotate(totale=Sum("importo"))
        .filter(totale__gt=Decimal("0"))
        .order_by("partecipazione__gruppo")
    )
    # .attivi(anno) esclude i gruppi disattivati per l'anno della campagna
    # (D-24/A-10): le loro partecipazioni restano congelate in
    # ContributoPartecipazione ma non vengono pagate, e la somma esclusa
    # resta semplicemente fuori dal totale generato (residuo alla Zona).
    gruppi = {
        g.codice: g
        for g in Gruppo.objects.attivi(campagna.anno).filter(
            codice__in=[r["partecipazione__gruppo"] for r in totali]
        )
    }

    righe = []
    for riga in totali:
        gruppo = gruppi.get(riga["partecipazione__gruppo"])
        if gruppo is None:
            continue
        righe.append(
            RigaBonifico(
                gruppo_codice=gruppo.codice,
                denominazione=gruppo.nome,
                intestazione_conto=gruppo.intestazione_conto,
                iban=gruppo.iban,
                importo=riga["totale"],
                causale=causale,
            )
        )
    return righe
