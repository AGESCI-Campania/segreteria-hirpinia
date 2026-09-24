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


def _e_admin_diretto(utente: Utente) -> bool:
    """ADMIN diretto (o superuser), mai per delega — condizione comune a
    `puo_impersonare()` e `puo_impersonare_qualcuno()` (D-27)."""
    if utente.is_superuser:
        return True
    oggi = timezone.localdate()
    return (
        Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.ADMIN, attivo=True)
        .filter(_non_scaduto("data_fine", oggi))
        .exists()
    )


def puo_impersonare(*, hijacker: Utente, hijacked: Utente) -> bool:
    """Callback per HIJACK_PERMISSION_CHECK (D-27): solo ADMIN, mai per delega.
    Interroga `Ruolo` direttamente e non `ruoli_effettivi()`, che includerebbe
    anche un ADMIN detenuto solo per delega — eccezione dichiarata, perché D-27
    esclude esplicitamente quel caso."""
    if not hijacked or hijacker.pk == hijacked.pk:
        return False
    return _e_admin_diretto(hijacker)


def puo_impersonare_qualcuno(utente: Utente) -> bool:
    """Vero se l'utente potrebbe impersonarne almeno un altro (D-27): usato per
    decidere se mostrare la voce nel menu. L'autorizzazione sul singolo
    bersaglio resta `puo_impersonare()`, invocata da HIJACK_PERMISSION_CHECK
    ad ogni richiesta di hijack — questa funzione non la sostituisce."""
    return _e_admin_diretto(utente)


def utenti_con_ruoli(tipi, *, alla_data: date | None = None) -> QuerySet[Utente]:
    """Direzione inversa di `ruoli_effettivi()` (D-28): dato un insieme di
    tipi di ruolo, tutti gli utenti che li detengono in modo effettivo —
    diretto o per delega, entrambi attivi e non scaduti, stessa logica di
    `ruoli_effettivi()` applicata alla relazione inversa invece che iterando
    utente per utente. Usata da `apps/note_spese/report_gestori.py` (D-64)
    per i destinatari selezionati per categoria di ruolo."""
    alla_data = alla_data or timezone.localdate()
    diretti = Q(ruoli__tipo__in=tipi, ruoli__attivo=True) & _non_scaduto(
        "ruoli__data_fine", alla_data
    )
    per_delega = (
        Q(
            deleghe_ricevute__ruolo__tipo__in=tipi,
            deleghe_ricevute__attiva=True,
            deleghe_ricevute__data_fine__gte=alla_data,
            deleghe_ricevute__ruolo__attivo=True,
        )
    ) & _non_scaduto("deleghe_ricevute__ruolo__data_fine", alla_data)
    return Utente.objects.filter(diretti | per_delega).distinct()
