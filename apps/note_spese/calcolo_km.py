"""Determinazione della fascia tariffaria e lookup della tariffa vigente
(D-52). Non calcola ancora l'importo di una riga (D-53, aggregazione andata/
ritorno vs per-riga): qui c'è solo il pezzo riusabile da entrambi i casi."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import FasciaTariffaChilometrica, TariffaChilometrica

SOGLIA_KM = Decimal("200")
SOGLIA_PASSEGGERI_TRE_O_PIU = 3


def fascia_per(passeggeri: int, km: Decimal) -> str:
    """D-52: 3+ passeggeri (conducente incluso) è sempre la fascia più alta,
    indipendentemente dalla distanza; sotto i 3, la soglia dei 200 km separa
    le altre due fasce (oltre i 200 km la tariffa più bassa si applica a
    **tutti** i km, non solo agli eccedenti — per questo qui basta la
    fascia, il calcolo dell'importo totale è altrove, D-53)."""
    if passeggeri >= SOGLIA_PASSEGGERI_TRE_O_PIU:
        return FasciaTariffaChilometrica.TRE_O_PIU
    if km <= SOGLIA_KM:
        return FasciaTariffaChilometrica.BREVE
    return FasciaTariffaChilometrica.LUNGA


def tariffa_km(fascia: str, data: datetime.date) -> Decimal:
    """D-52: tariffa vigente alla data della spesa (decisione presa con
    Andrea, 2026-09-16) — mai indovinata se manca una tariffa applicabile
    per quella fascia/data (anti-confabulazione)."""
    tariffa = (
        TariffaChilometrica.objects.filter(fascia=fascia, valida_dal__lte=data)
        .filter(Q(valida_al__isnull=True) | Q(valida_al__gte=data))
        .order_by("-valida_dal")
        .first()
    )
    if tariffa is None:
        raise ValidationError(
            f"Nessuna tariffa chilometrica configurata per la fascia {fascia} alla data {data}."
        )
    return tariffa.importo_km
