"""Unica fonte di verità sulla visibilità delle partecipazioni (D-13). M4
implementa solo il ramo pre-`CHIUSA` (ogni gruppo vede solo le proprie): nessuna
Campagna può raggiungere CHIUSA in M4 poiché nessuna transizione FSM con
effetti di dominio esiste ancora. Il ramo post-chiusura (totali cross-gruppo)
si aggiunge in M7 sotto la stessa firma."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import Utente
from apps.accounts.permessi import gruppi_visibili

from .models import Campagna, Partecipazione


def partecipazioni_visibili(utente: Utente, campagna: Campagna) -> QuerySet[Partecipazione]:
    gruppi = gruppi_visibili(utente, campagna.anno)
    return Partecipazione.objects.filter(campagna=campagna, gruppo__in=gruppi)
