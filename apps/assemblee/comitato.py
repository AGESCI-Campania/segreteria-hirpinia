"""Comitato elettorale di un'assemblea (D-70). Unico punto per aggiungere e
togliere componenti e per dar loro l'accesso a Catello.

Un componente è un avente diritto dell'elenco. Con l'accesso riceve un account
personale (creato qui se non esiste, senza password) e l'invito di
attivazione di D-20: fino a quando non imposta la password non può entrare.
Senza accesso compare solo nel verbale. Il componente si può aggiungere in
qualunque momento prima della conclusione dell'assemblea; toglierlo dal
comitato non tocca l'account, che senza nomina non vede le assemblee."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from apps.accounts.inviti import crea_invito
from apps.accounts.models import StatoUtente, TipoUtente, Utente

from .models import Assemblea, AventeDiritto, OperatoreVoto
from .permessi import puo_gestire_assemblee

logger = logging.getLogger(__name__)


class InvitoNonInviato(Exception):
    """La nomina è registrata ma l'email di invito non è partita."""


def _verifica(utente: Utente, assemblea: Assemblea) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")


def _account_esistente(avente: AventeDiritto) -> Utente | None:
    filtro = Q()
    if avente.codice_socio:
        filtro |= Q(codice_socio=avente.codice_socio)
    if avente.email:
        filtro |= Q(email__iexact=avente.email)
    if not filtro:
        return None
    # Il codice socio identifica la persona meglio dell'email.
    trovati = sorted(
        Utente.objects.filter(filtro),
        key=lambda u: u.codice_socio != (avente.codice_socio or None),
    )
    return trovati[0] if trovati else None


def _crea_account(avente: AventeDiritto) -> Utente:
    if not avente.email:
        raise ValidationError(
            "Per creare l'account serve l'email del capo: inseriscila nell'elenco, oppure "
            "aggiungilo al comitato senza accesso."
        )
    codice_socio = avente.codice_socio or None
    if codice_socio and Utente.objects.filter(codice_socio=codice_socio).exists():
        codice_socio = None
    utente = Utente(
        email=avente.email,
        username=avente.email,
        first_name=avente.nome,
        last_name=avente.cognome,
        codice_socio=codice_socio,
        tipo=TipoUtente.PERSONA,
        stato=StatoUtente.ATTIVO,
    )
    # Nessuna password finché il capo non la imposta con l'invito (D-20).
    utente.set_unusable_password()
    utente.full_clean(exclude=["password"])
    utente.save()
    return utente


def _collega_account(componente: OperatoreVoto) -> Utente:
    assert componente.avente is not None
    utente = _account_esistente(componente.avente) or _crea_account(componente.avente)
    if utente.tipo != TipoUtente.PERSONA:
        raise ValidationError(
            "L'email del capo è quella di un account di gruppo: correggila nell'elenco."
        )
    if (
        OperatoreVoto.objects.filter(assemblea=componente.assemblea, utente=utente)
        .exclude(pk=componente.pk)
        .exists()
    ):
        raise ValidationError("Questo account fa già parte del comitato elettorale.")
    componente.utente = utente
    componente.save(update_fields=["utente"])
    return utente


def _invia_invito(utente: Utente, gestore: Utente) -> bool:
    """Invito solo a chi non ha ancora una password. Fuori dalla transazione:
    un invio fallito non annulla la nomina, l'invito si può rimandare."""
    if utente.has_usable_password():
        return False
    try:
        crea_invito(email=utente.email, creato_da=gestore)
    except Exception:
        logger.exception("Invio dell'invito al comitato elettorale non riuscito (1 destinatario)")
        raise InvitoNonInviato from None
    return True


def aggiungi(
    assemblea: Assemblea, avente: AventeDiritto, gestore: Utente, *, accesso: bool = True
) -> tuple[OperatoreVoto, bool]:
    """Restituisce il componente e se è partito un invito di attivazione."""
    _verifica(gestore, assemblea)
    if avente.assemblea_id != assemblea.pk or avente.eliminato_il is not None:
        raise ValidationError("Il capo non è nell'elenco degli aventi diritto.")
    with transaction.atomic():
        if OperatoreVoto.objects.filter(assemblea=assemblea, avente=avente).exists():
            raise ValidationError("Il capo fa già parte del comitato elettorale.")
        componente = OperatoreVoto.objects.create(
            assemblea=assemblea, avente=avente, nominato_da=gestore
        )
        utente = _collega_account(componente) if accesso else None
    return componente, utente is not None and _invia_invito(utente, gestore)


def dai_accesso(componente: OperatoreVoto, gestore: Utente) -> bool:
    """Crea l'account a un componente che non l'ha, oppure rimanda l'invito a
    chi non ha ancora impostato la password. Restituisce se è partito."""
    _verifica(gestore, componente.assemblea)
    with transaction.atomic():
        utente = componente.utente or _collega_account(componente)
    return _invia_invito(utente, gestore)


@transaction.atomic
def rimuovi(componente: OperatoreVoto, gestore: Utente) -> None:
    _verifica(gestore, componente.assemblea)
    componente.delete()


def componenti(assemblea: Assemblea):
    return assemblea.operatori.select_related("avente", "avente__gruppo", "utente").order_by(
        "avente__cognome", "avente__nome", "utente__last_name"
    )
