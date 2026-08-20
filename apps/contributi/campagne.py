"""Apertura di una campagna (§7 passo 1). Chi imposta budget/tetto/finestra è
ristretto ai ruoli da SEGRETERIA in su, **esclusi i delegati** (D-11) — un
vincolo diverso dal solito perimetro per gruppo, quindi verificato qui nel
service layer come difesa in profondità, non solo nel mixin della view."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.audit import vieta_in_impersonificazione
from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import ruoli_effettivi
from apps.organizzazione.iban import valida_iban
from apps.organizzazione.models import Gruppo

from .calcolo import calcola_importi
from .models import (
    Campagna,
    ContributoPartecipazione,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
)

RUOLI_GESTIONE_CAMPAGNA = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


def _verifica_ruolo_diretto_gestione_campagna(utente: Utente) -> None:
    ruoli = ruoli_effettivi(utente)
    if not any(r.tipo in RUOLI_GESTIONE_CAMPAGNA and not r.is_delega for r in ruoli):
        raise PermissionDenied(
            f"{utente}: i parametri di campagna sono riservati a SEGRETERIA/ADMIN/RDZ, "
            "esclusi i delegati (D-11)."
        )


def verifica_ruolo_gestione_campagna(utente: Utente) -> None:
    """Come `_verifica_ruolo_diretto_gestione_campagna`, ma senza escludere i
    delegati: l'esclusione (D-11) vale solo per budget/tetto/finestra, non per
    avviare la valutazione, simulare o chiudere la campagna (D-12: "Segreteria+"
    senza la clausola "esclusi i delegati")."""
    ruoli = ruoli_effettivi(utente)
    if not any(r.tipo in RUOLI_GESTIONE_CAMPAGNA for r in ruoli):
        raise PermissionDenied(
            f"{utente}: azione riservata a SEGRETERIA/ADMIN/RDZ (anche per delega)."
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


@transaction.atomic
def avvia_valutazione(*, utente: Utente, campagna: Campagna) -> Campagna:
    """APERTA → IN_VALUTAZIONE (D-12, §7 passo 3). Il blocco dell'inserimento
    è già garantito da `inserimento.py`/`importazione_partecipazioni.py`, che
    richiedono `stato == APERTA`: qui basta cambiare stato. Le tipologie ad
    approvazione automatica (CFM/CFA/CCG, D-11) passano subito ad APPROVATA,
    una per una così che ognuna passi da `full_clean(exclude=["stato"])`."""
    verifica_ruolo_gestione_campagna(utente)
    if campagna.stato != StatoCampagna.APERTA:
        raise ValidationError(
            "La campagna non è APERTA: impossibile avviare la valutazione (D-12)."
        )

    campagna.avvia_valutazione()
    campagna.full_clean(exclude=["stato"])
    campagna.save()

    ora = timezone.now()
    auto_approvabili = Partecipazione.objects.filter(
        campagna=campagna,
        stato=StatoPartecipazione.INSERITA,
        tipologia__approvazione_automatica=True,
    )
    for partecipazione in auto_approvabili:
        partecipazione.approva()
        partecipazione.valutata_da = utente
        partecipazione.data_valutazione = ora
        partecipazione.full_clean(exclude=["stato"])
        partecipazione.save()

    return campagna


@vieta_in_impersonificazione("campagna_chiudi")
@transaction.atomic
def chiudi_campagna(request, *, utente: Utente, campagna: Campagna) -> Campagna:
    """IN_VALUTAZIONE → CHIUSA (D-12, D-14, §7 passo 5). Firma con `request`
    come primo argomento posizionale (diversa dalle altre funzioni di questo
    modulo): `vieta_in_impersonificazione` lo richiede per riconoscere una
    sessione impersonata (D-27)."""
    verifica_ruolo_gestione_campagna(utente)
    if campagna.stato != StatoCampagna.IN_VALUTAZIONE:
        raise ValidationError("La campagna non è IN_VALUTAZIONE: impossibile chiuderla (D-12).")

    if Partecipazione.objects.filter(
        campagna=campagna,
        stato__in=[StatoPartecipazione.INSERITA, StatoPartecipazione.DOCUMENTI_RICHIESTI],
    ).exists():
        raise ValidationError(
            "Ci sono partecipazioni non ancora valutate (INSERITA o DOCUMENTI_RICHIESTI): "
            "la chiusura non è consentita finché non sono tutte valutate (D-12)."
        )

    gruppi_da_pagare = Gruppo.objects.filter(
        partecipazioni__campagna=campagna,
        partecipazioni__stato=StatoPartecipazione.APPROVATA,
    ).distinct()
    non_validi = []
    for gruppo in gruppi_da_pagare:
        try:
            valida_iban(gruppo.iban)
        except ValidationError:
            non_validi.append(gruppo.codice)
    if non_validi:
        raise ValidationError(
            "IBAN mancante o non valido per i gruppi: " + ", ".join(sorted(non_validi)) + " (D-14)."
        )

    risultato = calcola_importi(campagna)
    ContributoPartecipazione.objects.filter(
        partecipazione__campagna=campagna, is_simulazione=True
    ).delete()
    ContributoPartecipazione.objects.bulk_create(
        ContributoPartecipazione(
            partecipazione_id=partecipazione_id, importo=importo, is_simulazione=False
        )
        for partecipazione_id, importo in risultato.importi.items()
    )

    campagna.chiudi()
    campagna.chiusa_il = timezone.now()
    campagna.full_clean(exclude=["stato"])
    campagna.save()
    return campagna
