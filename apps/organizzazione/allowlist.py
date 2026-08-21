"""Gestione applicativa dell'allowlist (D-06), da interfaccia invece che solo
da Django admin: stesso schema di controllo ruoli di `gruppi.py`, nessuna
dipendenza da `apps.contributi`."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Utente
from apps.accounts.permessi import ruoli_effettivi

from .gruppi import RUOLI_GESTIONE_GRUPPI
from .models import AllowlistGruppo, Gruppo, Origine


def _verifica_ruolo_gestione_allowlist(utente: Utente) -> None:
    ruoli = ruoli_effettivi(utente)
    if not any(r.tipo in RUOLI_GESTIONE_GRUPPI for r in ruoli):
        raise PermissionDenied(f"{utente}: azione riservata a SEGRETERIA/ADMIN/RDZ.")


def crea_voce_allowlist(*, utente: Utente, codice_gruppo: str, email: str) -> AllowlistGruppo:
    _verifica_ruolo_gestione_allowlist(utente)
    if not Gruppo.objects.filter(pk=codice_gruppo).exists():
        raise ValidationError(f"{codice_gruppo}: nessun gruppo con questo codice.")
    voce = AllowlistGruppo(
        codice_gruppo=codice_gruppo,
        email=email,
        origine=Origine.MANUALE,
        creata_da=utente,
    )
    voce.full_clean()
    voce.save()
    return voce


def elimina_voce_allowlist(*, utente: Utente, voce: AllowlistGruppo) -> None:
    _verifica_ruolo_gestione_allowlist(utente)
    voce.delete()
