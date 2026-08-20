"""Calcolo degli importi del contributo formazione capi (D-10). Unica fonte
di verità sul denaro: simulazione (`apps/contributi/simulazione.py`) e
chiusura (`apps/contributi/campagne.py::chiudi_campagna`) chiamano
`calcola_importi()` e basta, nessuna delle due reimplementa la formula."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from .models import Campagna, StatoPartecipazione


@dataclass(frozen=True)
class RisultatoCalcolo:
    n: int
    quota_proporzionale: Decimal
    residuo: Decimal
    importi: dict[int, Decimal]  # partecipazione_id -> importo, ROUND_DOWN a 2 decimali


def calcola_importi(campagna: Campagna) -> RisultatoCalcolo:
    """Formula D-10: `importo_i = min(B/N, tetto, quota_versata_i)`, troncato
    a 2 decimali per difetto. `B/N` non è mai arrotondato prima del `min()`,
    solo il risultato finale lo è: il troncamento per difetto garantisce
    `Σ importo_i ≤ B` in ogni caso."""
    budget = campagna.budget
    tetto = campagna.tetto_per_partecipazione
    approvate = campagna.partecipazioni.filter(stato=StatoPartecipazione.APPROVATA).only(
        "id", "quota_versata"
    )
    n = approvate.count()

    if n == 0:
        return RisultatoCalcolo(n=0, quota_proporzionale=budget, residuo=budget, importi={})

    quota_proporzionale = budget / n
    importi = {
        p.id: min(quota_proporzionale, tetto, p.quota_versata).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        for p in approvate
    }
    residuo = budget - sum(importi.values(), Decimal("0"))
    return RisultatoCalcolo(
        n=n, quota_proporzionale=quota_proporzionale, residuo=residuo, importi=importi
    )
