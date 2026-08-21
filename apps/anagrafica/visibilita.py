"""Perimetro dei capi visibili (D-34): funzione simmetrica a
`apps.accounts.permessi.gruppi_visibili()`, che resta l'unico punto che
risolve il perimetro sui gruppi. Un gruppo vede i capi censiti presso di sé
E quelli che vi prestano servizio pur essendo censiti altrove — le due
relazioni vanno considerate entrambe, mai una sola."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import Utente
from apps.accounts.permessi import gruppi_visibili

from .models import CensimentoCapo


def capi_visibili(utente: Utente, anno: int) -> QuerySet[CensimentoCapo]:
    gruppi = {g.codice for g in gruppi_visibili(utente, anno)}
    return (
        CensimentoCapo.objects.filter(anno_scout=anno)
        .filter(
            Q(gruppo__codice__in=gruppi)
            | Q(
                capo__incarichi__anno_scout=anno,
                capo__incarichi__cessato_il__isnull=True,
                capo__incarichi__gruppo_servizio__codice__in=gruppi,
            )
        )
        .distinct()
    )
