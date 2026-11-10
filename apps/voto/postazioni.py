"""Seggi (docs/plan_voto.md, flusso 3): unico punto delle regole.

Un operatore crea la postazione e apre sul tablet il link di attivazione,
valido una volta sola. L'attivazione lascia sul dispositivo un cookie firmato
con un segreto casuale, di cui il database conserva solo l'hash: senza quel
cookie un dispositivo non è un seggio. Disattivare la postazione la esclude
subito dall'urna."""

from __future__ import annotations

import secrets

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.accounts.models import Utente
from apps.assemblee.models import Seduta
from apps.assemblee.permessi import puo_operare

from .models import Postazione

COOKIE = "voto_postazione"
_SALE = "apps.voto.postazioni"


def _hash(segreto: str) -> str:
    return salted_hmac(_SALE, segreto, algorithm="sha256").hexdigest()


def _verifica_operatore(utente: Utente, seduta: Seduta) -> None:
    if not puo_operare(utente, seduta.assemblea):
        raise PermissionDenied
    if not seduta.assemblea.voto_catello:
        raise ValidationError("Questa assemblea non usa il voto elettronico di Catello.")


@transaction.atomic
def crea(seduta: Seduta, nome: str, utente: Utente) -> tuple[Postazione, str]:
    """Nuova postazione; restituisce anche il segreto del link di attivazione,
    che si mostra una volta sola."""
    _verifica_operatore(utente, seduta)
    if seduta.chiusa_il is not None:
        raise ValidationError("La seduta è chiusa.")
    nome = " ".join(nome.split())
    if not nome:
        raise ValidationError("Dai un nome alla postazione (es. «Seggio 1»).")
    segreto = secrets.token_urlsafe(24)
    postazione = Postazione.objects.create(
        seduta=seduta, nome=nome, attivazione_hash=_hash(segreto), creata_da=utente
    )
    return postazione, segreto


@transaction.atomic
def attiva(segreto_attivazione: str) -> tuple[Postazione, str] | None:
    """Consuma il link di attivazione: restituisce la postazione e il valore
    del cookie da lasciare sul dispositivo, oppure None se il link non vale."""
    postazione = (
        Postazione.objects.select_for_update()
        .filter(attivazione_hash=_hash(segreto_attivazione), attivata_il__isnull=True, attiva=True)
        .first()
    )
    if postazione is None or postazione.seduta.chiusa_il is not None:
        return None
    token = secrets.token_urlsafe(32)
    postazione.token_hash = _hash(token)
    postazione.attivata_il = timezone.now()
    postazione.save(update_fields=["token_hash", "attivata_il"])
    return postazione, f"{postazione.pk}:{token}"


def dal_cookie(valore: str | None) -> Postazione | None:
    """La postazione riconosciuta dal cookie, se attiva e della seduta aperta."""
    if not valore or ":" not in valore:
        return None
    pk, token = valore.split(":", 1)
    if not pk.isdigit():
        return None
    postazione = (
        Postazione.objects.filter(pk=int(pk), attiva=True, attivata_il__isnull=False)
        .select_related("seduta__assemblea")
        .first()
    )
    if postazione is None or not constant_time_compare(postazione.token_hash, _hash(token)):
        return None
    if not postazione.seduta.aperta:
        return None
    return postazione


@transaction.atomic
def disattiva(postazione: Postazione, utente: Utente) -> None:
    _verifica_operatore(utente, postazione.seduta)
    postazione.attiva = False
    postazione.save(update_fields=["attiva"])
