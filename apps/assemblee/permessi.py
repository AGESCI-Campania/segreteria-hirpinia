"""Permessi del modulo Assemblee (D-70). Riusa
`apps.accounts.permessi.tipi_ruolo_effettivi()`: nessuna query diretta su
`Ruolo`/`Delega` qui."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import tipi_ruolo_effettivi

from .models import RUOLI_CON_ACCESSO, Assemblea, IncaricoAssemblea, OperatoreVoto

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


def e_presidenza(utente: Utente, assemblea: Assemblea) -> bool:
    """Presidente o segretario con l'accesso (R4/D12)."""
    return IncaricoAssemblea.objects.filter(
        assemblea=assemblea, utente=utente, ruolo__in=RUOLI_CON_ACCESSO
    ).exists()


def puo_compilare_verbale(utente: Utente, assemblea: Assemblea) -> bool:
    """Verbale dell'assemblea: gestori, presidenti e segretario (D12-bis). La
    variazione del rappresentante legale resta ai gestori: contiene i dati
    anagrafici del Responsabile di Zona."""
    return puo_gestire_assemblee(utente) or e_presidenza(utente, assemblea)


def puo_vedere_odg(utente: Utente, assemblea: Assemblea) -> bool:
    """Ordine del giorno: lo modificano i gestori, presidenti e segretario lo
    vedono (D12-bis)."""
    return puo_compilare_verbale(utente, assemblea)


def assemblee_visibili(utente: Utente) -> QuerySet[Assemblea]:
    """I gestori vedono tutte le assemblee; un componente del comitato
    elettorale solo quelle non concluse per cui è stato nominato; presidenti e
    segretario anche dopo la conclusione, per il verbale."""
    if puo_gestire_assemblee(utente):
        return Assemblea.objects.all()
    comitato = Q(operatori__utente=utente, conclusa_il__isnull=True)
    presidenza = Q(incarichi__utente=utente, incarichi__ruolo__in=RUOLI_CON_ACCESSO)
    return Assemblea.objects.filter(comitato | presidenza).distinct()


def accede_assemblee(utente: Utente) -> bool:
    """Condizione per la voce di menu e l'accesso al modulo: un gestore sempre
    (deve poter creare la prima assemblea), gli altri solo se hanno
    un'assemblea visibile."""
    return puo_gestire_assemblee(utente) or assemblee_visibili(utente).exists()
