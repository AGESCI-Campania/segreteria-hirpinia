"""Unica fonte di verità sulla visibilità delle partecipazioni (D-13).
`partecipazioni_visibili()` copre "le proprie in dettaglio" per qualunque
stato di campagna. Il ramo post-chiusura ("+ totali degli altri gruppi") non
può condividere la stessa firma: un totale aggregato per gruppo non è una
`Partecipazione`. `totali_altri_gruppi()` copre quella parte con una forma
propria (deviazione dichiarata rispetto alla nota di M4, verificata in M7:
vedi memoria di progetto)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import QuerySet

from apps.accounts.models import Utente
from apps.accounts.permessi import gruppi_visibili

from .bonifici import genera_righe_bonifici
from .models import Campagna, Partecipazione, StatoCampagna

STATI_CON_VISIBILITA_CROSS_GRUPPO = frozenset({StatoCampagna.CHIUSA, StatoCampagna.LIQUIDATA})


def partecipazioni_visibili(utente: Utente, campagna: Campagna) -> QuerySet[Partecipazione]:
    gruppi = gruppi_visibili(utente, campagna.anno)
    return Partecipazione.objects.filter(campagna=campagna, gruppo__in=gruppi)


@dataclass(frozen=True)
class TotaleGruppo:
    gruppo_codice: str
    denominazione: str
    importo: Decimal


def totali_altri_gruppi(utente: Utente, campagna: Campagna) -> list[TotaleGruppo]:
    """D-13, dopo CHIUSA: un account di gruppo vede anche il totale (non il
    dettaglio nominativo) degli altri gruppi. Per un ruolo Zona
    `gruppi_visibili()` include già tutti i gruppi attivi, quindi la lista
    risulta sempre vuota — nessun branch esplicito sul tipo di account,
    sicura da chiamare per chiunque. Mai IBAN/intestazione_conto: assenti dal
    dataclass, non solo nascosti nel template (D-27)."""
    if campagna.stato not in STATI_CON_VISIBILITA_CROSS_GRUPPO:
        return []
    visibili = {g.codice for g in gruppi_visibili(utente, campagna.anno)}
    return [
        TotaleGruppo(
            gruppo_codice=riga.gruppo_codice, denominazione=riga.denominazione, importo=riga.importo
        )
        for riga in genera_righe_bonifici(campagna, causale="")
        if riga.gruppo_codice not in visibili
    ]
