"""Unica fonte di verità sui permessi (CLAUDE.md): nessuna view deve interrogare
direttamente `Ruolo`/`Delega`, né derivare il perimetro operativo da
`Utente.gruppo`, che identifica solo l'account funzionale (D-28/D-33)."""

from dataclasses import dataclass
from datetime import date

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.organizzazione.models import Gruppo

from .models import Delega, Ruolo, Utente

# Ruoli il cui perimetro è l'intera Zona (tutti i gruppi attivi), per contrasto
# con CG il cui perimetro è il solo gruppo assegnato al ruolo.
RUOLI_PERIMETRO_ZONA = frozenset(
    {
        Ruolo.Tipo.ADMIN,
        Ruolo.Tipo.SEGRETERIA,
        Ruolo.Tipo.RDZ,
        Ruolo.Tipo.AEZ,
        Ruolo.Tipo.MCZ,
        Ruolo.Tipo.IABZ,
        Ruolo.Tipo.ISZ,
    }
)


@dataclass(frozen=True)
class RuoloEffettivo:
    tipo: str
    gruppo: Gruppo | None
    branca: str
    settore: str
    is_delega: bool
    ruolo: Ruolo


def _non_scaduto(campo_data_fine: str, alla_data: date):
    return Q(**{f"{campo_data_fine}__isnull": True}) | Q(**{f"{campo_data_fine}__gte": alla_data})


def ruoli_effettivi(utente: Utente, *, alla_data: date | None = None) -> list[RuoloEffettivo]:
    """Unione dei ruoli diretti attivi e non scaduti e dei ruoli detenuti tramite
    delega attiva e non scaduta (D-04, D-28). La condizione sul ruolo di origine
    della delega realizza la revoca a cascata "lazy": se quel ruolo scade per
    data, la delega derivata smette di contare da sola, senza bisogno di
    scrivere Delega.attiva=False (la scrittura esplicita resta comunque
    necessaria per la revoca anticipata, vedi apps/accounts/deleghe.py)."""
    alla_data = alla_data or timezone.localdate()

    diretti = Ruolo.objects.filter(utente=utente, attivo=True).filter(
        _non_scaduto("data_fine", alla_data)
    )
    effettivi = [RuoloEffettivo(r.tipo, r.gruppo, r.branca, r.settore, False, r) for r in diretti]

    deleghe = (
        Delega.objects.filter(delegato=utente, attiva=True, data_fine__gte=alla_data)
        .select_related("ruolo", "ruolo__gruppo")
        .filter(ruolo__attivo=True)
        .filter(_non_scaduto("ruolo__data_fine", alla_data))
    )
    effettivi += [
        RuoloEffettivo(d.ruolo.tipo, d.ruolo.gruppo, d.ruolo.branca, d.ruolo.settore, True, d.ruolo)
        for d in deleghe
    ]
    return effettivi


def gruppi_visibili(utente: Utente, anno: int) -> QuerySet[Gruppo]:
    """Perimetro operativo dell'utente per `anno` (D-28): mai derivato da
    Utente.gruppo. Unione dei gruppi assegnati ai ruoli CG detenuti (diretti o
    per delega) e, se l'utente ha un ruolo di perimetro Zona, di tutti i gruppi
    attivi per quell'anno."""
    ruoli = ruoli_effettivi(utente, alla_data=timezone.localdate())

    if any(r.tipo in RUOLI_PERIMETRO_ZONA for r in ruoli):
        return Gruppo.objects.attivi(anno)

    codici_cg = {r.gruppo.codice for r in ruoli if r.tipo == Ruolo.Tipo.CG and r.gruppo}
    return Gruppo.objects.attivi(anno).filter(codice__in=codici_cg)


def puo_impersonare(*, hijacker: Utente, hijacked: Utente) -> bool:
    """Callback per HIJACK_PERMISSION_CHECK (D-27): solo ADMIN, mai per delega.
    Interroga `Ruolo` direttamente e non `ruoli_effettivi()`, che includerebbe
    anche un ADMIN detenuto solo per delega — eccezione dichiarata, perché D-27
    esclude esplicitamente quel caso."""
    if not hijacked or hijacker.pk == hijacked.pk:
        return False
    if hijacker.is_superuser:
        return True
    oggi = timezone.localdate()
    return (
        Ruolo.objects.filter(utente=hijacker, tipo=Ruolo.Tipo.ADMIN, attivo=True)
        .filter(_non_scaduto("data_fine", oggi))
        .exists()
    )
