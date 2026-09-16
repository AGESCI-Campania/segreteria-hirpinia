"""Cancellazione delle note (D-60/D-61). Non è una transizione FSM:
`eliminata_il` (soft delete) è indipendente da `stato`, e l'eliminazione
reale è una `delete()` vera e propria — mai confondere con `annulla()`
(F3), che è una transizione di stato visibile in storico, non un modo per
far sparire una nota.

Il capo (o il compilatore per conto terzi, D-36) può solo mettere le
proprie note in soft delete; segreteria/RdZ/admin scelgono anche la
cancellazione reale. **Nessuna cancellazione, in nessuna forma, su una nota
liquidata** (D-60): non solo la cancellazione reale, come si potrebbe
leggere isolando D-61 dal resto — D-60 pone il vincolo in modo generale
("una nota liquidata non è mai cancellabile"), qui applicato a entrambe le
funzioni."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Utente

from .models import NotaSpese, StatoNota
from .permessi import e_beneficiario_della_nota, e_compilatore_della_nota, puo_gestire_note


def _richiedi_non_liquidata(nota: NotaSpese) -> None:
    if nota.stato == StatoNota.LIQUIDATA:
        raise ValidationError("Una nota liquidata non è mai cancellabile (D-60).")


def elimina_nota_soft(nota: NotaSpese, utente: Utente) -> NotaSpese:
    """D-61: soft delete — disponibile al beneficiario/compilatore sulla
    propria nota, e a segreteria/RdZ/admin su qualsiasi nota."""
    _richiedi_non_liquidata(nota)
    autorizzato = (
        e_beneficiario_della_nota(utente, nota)
        or e_compilatore_della_nota(utente, nota)
        or puo_gestire_note(utente)
    )
    if not autorizzato:
        raise PermissionDenied(
            "Solo il beneficiario, chi ha compilato la nota o la gestione può eliminarla (D-61)."
        )
    nota.eliminata_il = timezone.now()
    nota.save(update_fields=["eliminata_il"])
    return nota


def elimina_nota_reale(nota: NotaSpese, utente: Utente) -> None:
    """D-61: cancellazione reale — riservata a segreteria/RdZ/admin, mai al
    beneficiario (motivazione nei requisiti: altrimenti basterebbe farlo per
    far sparire una nota respinta e la sua traccia)."""
    _richiedi_non_liquidata(nota)
    if not puo_gestire_note(utente):
        raise PermissionDenied(
            "Solo chi gestisce le note può cancellarla realmente, non il beneficiario (D-61)."
        )
    nota.delete()
