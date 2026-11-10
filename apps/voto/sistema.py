"""Sistema e modalità di voto di un'assemblea (docs/plan_voto.md).

Il sistema (app del Nazionale o voto di Catello) si sceglie alla creazione e
si può cambiare **fino all'apertura della prima votazione**: dopo, le
votazioni già aperte dipendono da quella scelta. La modalità (dispositivi
personali e seggi, oppure solo seggi) vale solo per il voto di Catello e si
cambia anche il giorno stesso."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import Utente
from apps.assemblee import elenco
from apps.assemblee.models import Assemblea, ModalitaVoto, SistemaVoto, Votazione
from apps.assemblee.permessi import puo_gestire_assemblee

from . import codici


def operazioni_di_voto_iniziate(assemblea: Assemblea) -> bool:
    return Votazione.objects.filter(seduta__assemblea=assemblea).exists()


@transaction.atomic
def imposta_sistema(assemblea: Assemblea, sistema: str, utente: Utente) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if sistema not in SistemaVoto.values:
        raise ValidationError("Sistema di voto non valido.")
    if sistema == assemblea.sistema_voto:
        return
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")
    if operazioni_di_voto_iniziate(assemblea):
        raise ValidationError(
            "Le votazioni sono già iniziate: il sistema di voto non si può più cambiare."
        )
    assemblea.sistema_voto = sistema
    assemblea.save(update_fields=["sistema_voto"])
    if sistema == SistemaVoto.NAZIONALE:
        codici.revoca_tutti(assemblea, utente)
    elenco.ricalcola_voto(assemblea)


@transaction.atomic
def imposta_modalita(assemblea: Assemblea, modalita: str, utente: Utente) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if modalita not in ModalitaVoto.values:
        raise ValidationError("Modalità di voto non valida.")
    if not assemblea.voto_catello:
        raise ValidationError("La modalità vale solo per il voto elettronico di Catello.")
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")
    assemblea.modalita_voto = modalita
    assemblea.save(update_fields=["modalita_voto"])
