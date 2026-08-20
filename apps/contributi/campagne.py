"""Apertura di una campagna (§7 passo 1). Chi imposta budget/tetto/finestra è
ristretto ai ruoli da SEGRETERIA in su, **esclusi i delegati** (D-11) — un
vincolo diverso dal solito perimetro per gruppo, quindi verificato qui nel
service layer come difesa in profondità, non solo nel mixin della view."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import ruoli_effettivi

from .models import Campagna

RUOLI_GESTIONE_CAMPAGNA = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


def _verifica_ruolo_diretto_gestione_campagna(utente: Utente) -> None:
    ruoli = ruoli_effettivi(utente)
    if not any(r.tipo in RUOLI_GESTIONE_CAMPAGNA and not r.is_delega for r in ruoli):
        raise PermissionDenied(
            f"{utente}: i parametri di campagna sono riservati a SEGRETERIA/ADMIN/RDZ, "
            "esclusi i delegati (D-11)."
        )


def apri_campagna(
    *,
    utente: Utente,
    anno: int,
    budget: Decimal,
    tetto_per_partecipazione: Decimal,
    data_inizio_inserimento: datetime.date,
    data_fine_inserimento: datetime.date,
) -> Campagna:
    _verifica_ruolo_diretto_gestione_campagna(utente)
    campagna = Campagna(
        anno=anno,
        budget=budget,
        tetto_per_partecipazione=tetto_per_partecipazione,
        data_inizio_inserimento=data_inizio_inserimento,
        data_fine_inserimento=data_fine_inserimento,
        creata_da=utente,
    )
    # exclude=["stato"]: FSMField(protected=True) blocca qualunque secondo
    # `setattr`, incluso quello che clean_fields() esegue per ogni campo del
    # form di validazione anche quando il valore non cambia (verificato sul
    # sorgente di django-fsm-2). `stato` non è mai un input qui (resta il
    # default APERTA), quindi escluderlo dalla validazione non perde nulla.
    campagna.full_clean(exclude=["stato"])
    campagna.save()
    return campagna
