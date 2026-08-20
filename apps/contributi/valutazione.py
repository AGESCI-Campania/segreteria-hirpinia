"""Valutazione delle partecipazioni (D-11, D-12, §7 passo 3): le tipologie
non ad approvazione automatica sono valutate dal Comitato di Zona, con
facoltà di richiedere documentazione. Il gruppo che ha inserito la
partecipazione non può mai valutarla (CG escluso, conflitto di interesse) —
decisione confermata con l'utente in fase di pianificazione di M5."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import gruppi_visibili, ruoli_effettivi

from .models import AllegatoPartecipazione, Partecipazione, StatoCampagna, StatoPartecipazione

RUOLI_VALUTAZIONE_PARTECIPAZIONI = frozenset(
    {Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ, Ruolo.Tipo.MCZ}
)


def _verifica_ruolo_valutazione(utente: Utente) -> None:
    ruoli = ruoli_effettivi(utente)
    if not any(r.tipo in RUOLI_VALUTAZIONE_PARTECIPAZIONI for r in ruoli):
        raise PermissionDenied(
            f"{utente}: la valutazione delle partecipazioni è riservata a "
            "SEGRETERIA/ADMIN/RDZ/MCZ, mai al gruppo che le ha inserite (CG)."
        )


def _verifica_in_valutazione(partecipazione: Partecipazione) -> None:
    if partecipazione.campagna.stato != StatoCampagna.IN_VALUTAZIONE:
        raise ValidationError(
            "La campagna non è IN_VALUTAZIONE: nessuna valutazione è possibile ora (D-12)."
        )


@transaction.atomic
def approva_partecipazione(*, utente: Utente, partecipazione: Partecipazione) -> Partecipazione:
    _verifica_ruolo_valutazione(utente)
    _verifica_in_valutazione(partecipazione)
    partecipazione.approva()
    partecipazione.valutata_da = utente
    partecipazione.data_valutazione = timezone.now()
    partecipazione.full_clean(exclude=["stato"])
    partecipazione.save()
    return partecipazione


@transaction.atomic
def respingi_partecipazione(
    *, utente: Utente, partecipazione: Partecipazione, motivazione: str
) -> Partecipazione:
    _verifica_ruolo_valutazione(utente)
    _verifica_in_valutazione(partecipazione)
    if not motivazione.strip():
        raise ValidationError(
            "Un respingimento senza causale non è possibile, in nessun percorso (D-12/D-24)."
        )
    partecipazione.respingi()
    partecipazione.motivazione_respingimento = motivazione
    partecipazione.valutata_da = utente
    partecipazione.data_valutazione = timezone.now()
    partecipazione.full_clean(exclude=["stato"])
    partecipazione.save()
    return partecipazione


@transaction.atomic
def richiedi_documenti(*, utente: Utente, partecipazione: Partecipazione) -> Partecipazione:
    """Non tocca `valutata_da`/`data_valutazione`: quei campi tracciano l'esito
    finale (approvazione/respingimento), non la richiesta intermedia."""
    _verifica_ruolo_valutazione(utente)
    _verifica_in_valutazione(partecipazione)
    partecipazione.richiedi_documenti()
    partecipazione.full_clean(exclude=["stato"])
    partecipazione.save()
    return partecipazione


@transaction.atomic
def carica_allegato(
    *, utente: Utente, partecipazione: Partecipazione, file, tipo: str = ""
) -> AllegatoPartecipazione:
    """Caricamento a cura del gruppo (o dello staff Zona) in risposta a una
    richiesta di documentazione (D-11): non obbligatorio nel flusso ordinario,
    esiste solo per il ramo DOCUMENTI_RICHIESTI. Non fa avanzare lo stato: la
    valutazione successiva resta un'azione separata del Comitato."""
    visibili = {g.codice for g in gruppi_visibili(utente, partecipazione.campagna.anno)}
    if partecipazione.gruppo_id not in visibili:
        raise PermissionDenied(f"{partecipazione.gruppo_id} non è nel perimetro di {utente}.")
    if partecipazione.stato != StatoPartecipazione.DOCUMENTI_RICHIESTI:
        raise ValidationError(
            "Nessun documento richiesto per questa partecipazione al momento (D-11)."
        )
    allegato = AllegatoPartecipazione(
        partecipazione=partecipazione, file=file, tipo=tipo, caricato_da=utente
    )
    allegato.full_clean()
    allegato.save()
    return allegato
