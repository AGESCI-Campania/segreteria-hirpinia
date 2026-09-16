"""Verifica di capienza dei centri di costo (D-47/D-48).

Il budget di un nodo è annuale e si consuma **solo** alla transizione verso
`LIQUIDATA`, mai in cascata su padre o figli (D-47): questa funzione calcola
il consumato di un singolo nodo per un singolo anno, senza aggregare
l'albero. Uno sforamento non è un errore da bloccare (deciso con Andrea,
2026-09-16, coerente con "sforamento resta sul figlio" letto come evento
normale): la funzione è pensata per essere richiamata sia da
`transizioni.liquida()` a fini di segnalazione non bloccante, sia dal
reporting di F6."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from .models import BudgetCentroCosto, CentroCosto, NotaSpese, StatoNota


@dataclass(frozen=True)
class CapienzaCentroCosto:
    budget: Decimal
    consumato: Decimal

    @property
    def residuo(self) -> Decimal:
        return self.budget - self.consumato


def capienza_centro_costo(centro_costo: CentroCosto, anno_scout: int) -> CapienzaCentroCosto:
    """`anno_scout` è l'anno associativo di **contabilizzazione** (D-47),
    coerente con `BudgetCentroCosto.anno_scout` e con `NotaSpese.anno_contabilizzazione`,
    non l'anno di spesa."""
    budget_riga = BudgetCentroCosto.objects.filter(
        centro_costo=centro_costo, anno_scout=anno_scout
    ).first()
    budget = budget_riga.importo if budget_riga else Decimal("0")

    totale = NotaSpese.objects.filter(
        centro_costo=centro_costo,
        anno_contabilizzazione=anno_scout,
        stato=StatoNota.LIQUIDATA,
    ).aggregate(totale=Sum("righe__importo"))["totale"]
    consumato = totale if totale is not None else Decimal("0")

    return CapienzaCentroCosto(budget=budget, consumato=consumato)
