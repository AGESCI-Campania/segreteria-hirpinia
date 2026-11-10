"""Deleghe degli AE (regolamento art. 5, D-70): unico punto delle regole.

- Delega solo l'AE di gruppo (dagli incarichi) o l'AE di Zona (segnato a mano).
  Gli AE di unità non delegano.
- L'AE di gruppo delega un componente della propria Co.Ca. (un capo del suo
  gruppo) o un altro AE; l'AE di Zona un Responsabile di Zona o un membro del
  Comitato (un RdZ è anche membro del Comitato).
- Nessuno raccoglie più di una delega; un AE delega una sola volta per seduta;
  chi ha delegato non riceve deleghe e chi ne ha ricevuta una non delega."""

from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import Utente
from apps.anagrafica.models import FunzioneIncarico, IncaricoUnita

from .models import AventeDiritto, DelegaAE, IncaricoDichiarato, Seduta
from .permessi import puo_gestire_assemblee, puo_operare


def ae_gruppo_ids(aventi: Iterable[AventeDiritto]) -> set[int]:
    """Unica regola dell'AE di gruppo, su più aventi insieme (una query per
    fonte): incarico "AE di gruppo" nelle autorizzazioni dell'anno da cui
    arriva il capo, o fra gli incarichi dichiarati se inserito a mano."""
    aventi = list(aventi)
    dichiarati = set(
        IncaricoDichiarato.objects.filter(
            avente__in=aventi, funzione=FunzioneIncarico.AE_GRUPPO
        ).values_list("avente_id", flat=True)
    )
    da_autorizzazioni = set(
        IncaricoUnita.objects.filter(
            capo_id__in=[a.codice_socio for a in aventi if a.codice_socio],
            funzione=FunzioneIncarico.AE_GRUPPO,
            cessato_il__isnull=True,
        ).values_list("capo_id", "anno_scout")
    )
    return {
        a.pk
        for a in aventi
        if a.pk in dichiarati or (a.codice_socio, a.anno_censimento) in da_autorizzazioni
    }


def e_ae_gruppo(avente: AventeDiritto) -> bool:
    return avente.pk in ae_gruppo_ids([avente])


def e_ae(avente: AventeDiritto) -> bool:
    return avente.ae_zona or e_ae_gruppo(avente)


def possono_delegare(aventi: Iterable[AventeDiritto]) -> list[AventeDiritto]:
    """AE di gruppo e AE di Zona fra `aventi` (gli AE di unità non delegano)."""
    aventi = list(aventi)
    ae_gruppo = ae_gruppo_ids(aventi)
    return [a for a in aventi if a.ae_zona or a.pk in ae_gruppo]


def verifica_destinatario(delegante: AventeDiritto, delegato: AventeDiritto) -> None:
    """Solleva ValidationError se `delegato` non può ricevere la delega di
    `delegante` secondo l'art. 5."""
    if delegante.pk == delegato.pk:
        raise ValidationError("Un AE non può delegare se stesso.")
    if delegante.ae_zona:
        if not (delegato.rdz or delegato.comitato):
            raise ValidationError(
                "L'AE di Zona può delegare solo un Responsabile di Zona o un membro del Comitato."
            )
        return
    if not e_ae_gruppo(delegante):
        raise ValidationError("Può delegare solo l'AE di gruppo o l'AE di Zona.")
    if delegato.gruppo_id != delegante.gruppo_id and not e_ae(delegato):
        raise ValidationError(
            "L'AE di gruppo può delegare solo un capo del proprio gruppo o un altro AE."
        )


def _verifica_operatore(utente: Utente, seduta: Seduta) -> None:
    if not puo_operare(utente, seduta.assemblea):
        raise PermissionDenied


@transaction.atomic
def registra_delega(
    seduta: Seduta, delegante: AventeDiritto, delegato: AventeDiritto, utente: Utente
) -> DelegaAE:
    _verifica_operatore(utente, seduta)
    if seduta.chiusa_il is not None:
        raise ValidationError("La seduta è chiusa.")
    for avente in (delegante, delegato):
        if avente.assemblea_id != seduta.assemblea_id or avente.eliminato:
            raise ValidationError(f"{avente} non è nell'elenco degli aventi diritto.")
    verifica_destinatario(delegante, delegato)
    deleghe = seduta.deleghe
    if deleghe.filter(delegante=delegante).exists():
        raise ValidationError(f"{delegante} ha già delegato in questa seduta.")
    if deleghe.filter(delegato=delegato).exists():
        raise ValidationError(f"{delegato} ha già una delega: non può raccoglierne un'altra.")
    if deleghe.filter(delegante=delegato).exists():
        raise ValidationError(f"{delegato} ha delegato a sua volta: non può ricevere deleghe.")
    if deleghe.filter(delegato=delegante).exists():
        raise ValidationError(f"{delegante} ha ricevuto una delega: non può delegare.")
    try:
        return DelegaAE.objects.create(
            seduta=seduta, delegante=delegante, delegato=delegato, registrata_da=utente
        )
    except IntegrityError as errore:  # registrazione concorrente dallo stesso banco
        raise ValidationError("Delega già registrata.") from errore


@transaction.atomic
def revoca_delega(delega: DelegaAE, utente: Utente) -> None:
    _verifica_operatore(utente, delega.seduta)
    if delega.seduta.chiusa_il is not None:
        raise ValidationError("La seduta è chiusa.")
    delega.delete()


@transaction.atomic
def aggiorna_qualifiche(
    avente: AventeDiritto, utente: Utente, *, ae_zona: bool, rdz: bool, comitato: bool
) -> None:
    """AE di Zona, RdZ e membri del Comitato si segnano a mano (D-70)."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if avente.assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")
    if (
        ae_zona
        and avente.assemblea.aventi_diritto.filter(ae_zona=True).exclude(pk=avente.pk).exists()
    ):
        raise ValidationError("C'è già un AE di Zona in questa assemblea.")
    avente.ae_zona = ae_zona
    avente.rdz = rdz
    # Un RdZ è anche membro del Comitato.
    avente.comitato = comitato or rdz
    avente.save(update_fields=["ae_zona", "rdz", "comitato"])
