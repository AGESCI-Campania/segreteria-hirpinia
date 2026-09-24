"""Validazione e fusione degli eventi (D-49): operazioni nel service layer,
mai una sequenza di update da view — un'eventuale API futura deve chiamare
queste stesse funzioni (D-69).

Il tracciamento in auditlog di "evento di origine e destinazione" non
richiede una scrittura manuale di `LogEntry`: `NotaSpese` è già registrata
in `auditlog` (apps.py), quindi riassegnare il campo `evento` con `.save()`
riga per riga (mai `.update()`, che bypassa i signal) produce di per sé una
voce con `changes["evento"] = [origine_pk, destinazione_pk]` per ciascuna
nota spostata — stesso pattern già in uso per la riattribuzione delle
partecipazioni al trasferimento di un capo
(`apps.contributi.trasferimenti.riattribuisci_partecipazioni`)."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import Utente

from .models import Evento, NotaSpese
from .permessi import puo_gestire_note


def valida_evento(evento: Evento, utente: Utente) -> Evento:
    """D-49: chi gestisce le note valida un evento creato da un capo. Non è
    una macchina a stati (niente `@transition`, `validato` è un semplice
    booleano) — idempotente, rivalidare un evento già validato non è un
    errore."""
    if not puo_gestire_note(utente):
        raise PermissionDenied("Solo chi gestisce le note può validare un evento (D-49).")
    evento.validato = True
    evento.save(update_fields=["validato"])
    return evento


def fondi_eventi(origine: Evento, destinazione: Evento, utente: Utente) -> list[NotaSpese]:
    """Riassegna a `destinazione` tutte le note di `origine`, poi elimina
    `origine`. Restituisce le note spostate. Riservata a chi gestisce le
    note (§2): la validazione/fusione degli eventi non è un'azione del capo
    che li crea."""
    if not puo_gestire_note(utente):
        raise PermissionDenied("Solo chi gestisce le note può fondere due eventi (D-49).")
    if origine.pk == destinazione.pk:
        raise ValidationError("Un evento non può essere fuso con se stesso.")

    with transaction.atomic():
        interessate = list(NotaSpese.objects.filter(evento=origine))
        for nota in interessate:
            nota.evento = destinazione
            nota.save(update_fields=["evento"])
        origine.delete()
    return interessate
