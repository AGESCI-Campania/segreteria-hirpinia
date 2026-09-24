"""Verifica di capienza dei centri di costo (D-47/D-48).

Il budget di un nodo è annuale e si consuma **solo** alla transizione verso
`LIQUIDATA`, mai in cascata su padre o figli (D-47): questa funzione calcola
il consumato di un singolo nodo per un singolo anno, senza aggregare
l'albero. Uno sforamento non è un errore da bloccare (deciso con Andrea,
2026-09-16, coerente con "sforamento resta sul figlio" letto come evento
normale): la funzione è pensata per essere richiamata sia da
`transizioni.liquida()` a fini di segnalazione non bloccante, sia dal
reporting/vista di verifica di F6 (`verifica.py`)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from .models import BudgetCentroCosto, CentroCosto, NotaSpese, StatoNota


@dataclass(frozen=True)
class CapienzaCentroCosto:
    budget: Decimal
    consumato: Decimal
    impegnato: Decimal = Decimal("0")

    @property
    def residuo(self) -> Decimal:
        """Solo il consumato certo (note liquidate) — D-48."""
        return self.budget - self.consumato

    @property
    def residuo_indicativo(self) -> Decimal:
        """Consumato + impegnato (approvato non liquidato) — D-48 impone di
        distinguere questo valore indicativo dal `residuo` certo: può
        cambiare se una nota approvata viene poi corretta o respinta prima
        della liquidazione."""
        return self.budget - self.consumato - self.impegnato


def capienza_centro_costo(centro_costo: CentroCosto, anno_scout: int) -> CapienzaCentroCosto:
    """`anno_scout` è l'anno associativo di **contabilizzazione** (D-47) per
    il `consumato` (coerente con `BudgetCentroCosto.anno_scout` e con
    `NotaSpese.anno_contabilizzazione`). Per l'`impegnato` non esiste un
    `anno_contabilizzazione` prima della liquidazione (D-41): si usa
    `anno_spesa` come proxy (decisione con Andrea, 2026-09-24), sapendo che
    può differire se la nota viene liquidata nell'anno successivo."""
    budget_riga = BudgetCentroCosto.objects.filter(
        centro_costo=centro_costo, anno_scout=anno_scout
    ).first()
    budget = budget_riga.importo if budget_riga else Decimal("0")

    totale_consumato = NotaSpese.objects.filter(
        centro_costo=centro_costo,
        anno_contabilizzazione=anno_scout,
        stato=StatoNota.LIQUIDATA,
    ).aggregate(totale=Sum("righe__importo"))["totale"]
    consumato = totale_consumato if totale_consumato is not None else Decimal("0")

    totale_impegnato = NotaSpese.objects.filter(
        centro_costo=centro_costo,
        anno_spesa=anno_scout,
        stato__in=(StatoNota.APPROVATA, StatoNota.AUTORIZZATA_RDZ),
    ).aggregate(totale=Sum("righe__importo"))["totale"]
    impegnato = totale_impegnato if totale_impegnato is not None else Decimal("0")

    return CapienzaCentroCosto(budget=budget, consumato=consumato, impegnato=impegnato)
