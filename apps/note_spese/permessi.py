"""Permessi del modulo Nota Spese (§2 dei requisiti). Riusa
`apps.accounts.permessi.ruoli_effettivi()` (D-69): nessuna query diretta su
`Ruolo`/`Delega` qui."""

from __future__ import annotations

from django.conf import settings

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import ruoli_effettivi

from .models import GenereRdz, NotaSpese

RUOLI_GESTIONE_NOTE = frozenset({Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ, Ruolo.Tipo.ADMIN})


def _tipi_ruolo(utente: Utente) -> set[str]:
    if utente.is_superuser:
        return {Ruolo.Tipo.ADMIN}
    return {r.tipo for r in ruoli_effettivi(utente)}


def puo_gestire_note(utente: Utente) -> bool:
    """Segreteria/RdZ/Admin (§2): verifica, edita, approva, respinge,
    registra il pagamento. Operativamente equivalenti (§2), nessuna
    distinzione qui fra segreteria e RdZ."""
    return bool(_tipi_ruolo(utente) & RUOLI_GESTIONE_NOTE)


def puo_autorizzare_rdz(utente: Utente) -> bool:
    """D-35: solo RdZ o Admin autorizzano, mai la segreteria da sola."""
    return bool(_tipi_ruolo(utente) & {Ruolo.Tipo.RDZ, Ruolo.Tipo.ADMIN})


def puo_modificare_impostazioni(utente: Utente) -> bool:
    """D-35: impostazione di sistema modificabile da admin e RdZ."""
    return bool(_tipi_ruolo(utente) & {Ruolo.Tipo.RDZ, Ruolo.Tipo.ADMIN})


def e_beneficiario_della_nota(utente: Utente, nota: NotaSpese) -> bool:
    return utente.codice_socio is not None and utente.codice_socio == nota.beneficiario_id


def genere_rdz(utente: Utente) -> str | None:
    """D-35: il genere si legge dall'email dell'account funzionale RdZ
    (`settings.NOTA_SPESE_RDZ_EMAIL_MASCHILE`/`_FEMMINILE`), mai da
    `Capo.sesso` (verificato non affidabile/non usato altrove in Catello).
    `None` se l'utente non usa nessuna delle due caselle configurate: chi
    chiama deve trattarlo come un errore esplicito, non indovinare."""
    email = (utente.email or "").strip().lower()
    if email == settings.NOTA_SPESE_RDZ_EMAIL_MASCHILE.strip().lower():
        return GenereRdz.MASCHILE
    if email == settings.NOTA_SPESE_RDZ_EMAIL_FEMMINILE.strip().lower():
        return GenereRdz.FEMMINILE
    return None
