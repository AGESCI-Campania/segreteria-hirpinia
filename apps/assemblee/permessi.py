"""Permessi del modulo Assemblee (D-70). Riusa
`apps.accounts.permessi.tipi_ruolo_effettivi()`: nessuna query diretta su
`Ruolo`/`Delega` qui."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import tipi_ruolo_effettivi

from .models import Assemblea, OperatoreVoto

RUOLI_GESTIONE_ASSEMBLEE = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


def puo_gestire_assemblee(utente: Utente) -> bool:
    """ADMIN, SEGRETERIA e RdZ: creano le assemblee, gestiscono l'elenco degli
    aventi diritto, nominano gli operatori di voto, scaricano i file."""
    return bool(tipi_ruolo_effettivi(utente) & RUOLI_GESTIONE_ASSEMBLEE)


def e_operatore(utente: Utente, assemblea: Assemblea) -> bool:
    return OperatoreVoto.objects.filter(assemblea=assemblea, utente=utente).exists()


def puo_operare(utente: Utente, assemblea: Assemblea) -> bool:
    """Operazioni di voto (presenze, deleghe, risultati): gestori e operatori
    nominati per quella assemblea."""
    return puo_gestire_assemblee(utente) or e_operatore(utente, assemblea)


def assemblee_visibili(utente: Utente) -> QuerySet[Assemblea]:
    """I gestori vedono tutte le assemblee; un operatore solo quelle non
    concluse per cui è stato nominato."""
    if puo_gestire_assemblee(utente):
        return Assemblea.objects.all()
    return Assemblea.objects.filter(operatori__utente=utente, conclusa_il__isnull=True)


def accede_assemblee(utente: Utente) -> bool:
    """Condizione per la voce di menu e l'accesso al modulo: un gestore sempre
    (deve poter creare la prima assemblea), un operatore solo se ha
    un'assemblea non conclusa."""
    return puo_gestire_assemblee(utente) or assemblee_visibili(utente).exists()
