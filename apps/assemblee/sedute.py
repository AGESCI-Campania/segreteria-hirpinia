"""Sedute e presenze (D-70): apertura, registrazione all'ingresso, esito sul
quorum costitutivo, convocazione successiva. Unico punto delle regole; le
view chiamano solo queste funzioni."""

from __future__ import annotations

import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente

from .models import Appello, Assemblea, AventeDiritto, Presenza, Seduta, TipoAppello
from .permessi import puo_gestire_assemblee, puo_operare
from .quorum import appello_attivo, stato_quorum


def _verifica_operatore(utente: Utente, seduta: Seduta) -> None:
    if not puo_operare(utente, seduta.assemblea):
        raise PermissionDenied


def _verifica_aperta(seduta: Seduta) -> None:
    if not seduta.aperta:
        raise ValidationError("La seduta non è aperta.")


def seduta_corrente(assemblea: Assemblea) -> Seduta | None:
    """L'ultima convocazione: quella a cui si riferiscono presenze e file."""
    return assemblea.sedute.order_by("-convocazione").first()


@transaction.atomic
def apri_seduta(seduta: Seduta, utente: Utente) -> None:
    """Apre la registrazione delle presenze, con l'appello d'ingresso."""
    _verifica_operatore(utente, seduta)
    if seduta.assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")
    if seduta.aperta_il is not None:
        raise ValidationError("La seduta è già stata aperta.")
    if seduta != seduta_corrente(seduta.assemblea):
        raise ValidationError("Si può aprire solo l'ultima convocazione.")
    seduta.aperta_il = timezone.now()
    seduta.save(update_fields=["aperta_il"])
    Appello.objects.create(seduta=seduta, numero=1, tipo=TipoAppello.INGRESSO, aperto_da=utente)


def _avente_della_seduta(seduta: Seduta, avente: AventeDiritto) -> None:
    if avente.assemblea_id != seduta.assemblea_id or avente.eliminato:
        raise ValidationError("Questo capo non è nell'elenco degli aventi diritto.")


@transaction.atomic
def registra_presenza(seduta: Seduta, avente: AventeDiritto, utente: Utente) -> bool:
    """Segna presente `avente` nell'appello attivo. Restituisce False se lo
    era già (un doppio tocco non è un errore)."""
    _verifica_operatore(utente, seduta)
    _verifica_aperta(seduta)
    _avente_della_seduta(seduta, avente)
    appello = appello_attivo(seduta)
    assert appello is not None
    _, creata = Presenza.objects.get_or_create(
        appello=appello, avente=avente, defaults={"registrata_da": utente}
    )
    return creata


@transaction.atomic
def annulla_presenza(seduta: Seduta, avente: AventeDiritto, utente: Utente) -> None:
    """Correzione di un errore di registrazione, non un'uscita: le uscite non
    si registrano (D-70); i presenti si aggiornano con la verifica del quorum."""
    _verifica_operatore(utente, seduta)
    _verifica_aperta(seduta)
    appello = appello_attivo(seduta)
    Presenza.objects.filter(appello=appello, avente=avente).delete()


@transaction.atomic
def dichiara_costituita(seduta: Seduta, utente: Utente) -> None:
    _verifica_operatore(utente, seduta)
    _verifica_aperta(seduta)
    if seduta.costituita is not None:
        raise ValidationError("L'esito della seduta è già stato dichiarato.")
    if not stato_quorum(seduta).raggiunto:
        raise ValidationError("Il quorum costitutivo non è raggiunto.")
    seduta.costituita = True
    seduta.save(update_fields=["costituita"])


@transaction.atomic
def dichiara_non_costituita(seduta: Seduta, utente: Utente) -> None:
    """Quorum non raggiunto: la seduta si chiude e se ne può convocare
    un'altra. In terza convocazione non si dà (nessun quorum)."""
    _verifica_operatore(utente, seduta)
    _verifica_aperta(seduta)
    if seduta.costituita is not None:
        raise ValidationError("L'esito della seduta è già stato dichiarato.")
    if stato_quorum(seduta).raggiunto:
        raise ValidationError("Il quorum costitutivo è raggiunto: la seduta è costituita.")
    seduta.costituita = False
    seduta.chiusa_il = timezone.now()
    seduta.save(update_fields=["costituita", "chiusa_il"])


@transaction.atomic
def chiudi_lavori(seduta: Seduta, utente: Utente) -> None:
    _verifica_operatore(utente, seduta)
    _verifica_aperta(seduta)
    if seduta.costituita is not True:
        raise ValidationError("Si chiudono i lavori solo di una seduta costituita.")
    seduta.chiusa_il = timezone.now()
    seduta.save(update_fields=["chiusa_il"])


@transaction.atomic
def crea_convocazione_successiva(
    assemblea: Assemblea,
    utente: Utente,
    *,
    data: datetime.date,
    ora: datetime.time | None = None,
    luogo: str = "",
) -> Seduta:
    """La data la decide il Consiglio di Zona: solo i gestori, solo dopo una
    seduta dichiarata non costituita, al massimo fino alla terza."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    ultima = seduta_corrente(assemblea)
    if ultima is None or ultima.costituita is not False:
        raise ValidationError(
            "Una nuova convocazione si crea solo dopo una seduta senza quorum costitutivo."
        )
    if ultima.convocazione >= Seduta.Convocazione.TERZA:
        raise ValidationError("La terza convocazione è l'ultima.")
    return Seduta.objects.create(
        assemblea=assemblea,
        convocazione=ultima.convocazione + 1,
        data=data,
        ora=ora,
        luogo=luogo,
    )
