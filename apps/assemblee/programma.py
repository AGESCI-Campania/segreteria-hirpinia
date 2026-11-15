"""Programma dei lavori della seduta (cronoprogramma): righe con ora di inizio,
ora di fine facoltativa, attività e punti dell'OdG facoltativi (anche più di
uno per riga). Lo preparano i
gestori, anche durante i lavori (ritardi), fino alla chiusura della seduta;
presidenti e segretario lo vedono e lo stampano, come l'ordine del giorno."""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Iterable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import Utente
from apps.core.pdf import contesto_carta_intestata

from .models import PuntoOdG, RigaProgramma, Seduta
from .permessi import puo_gestire_assemblee, puo_vedere_odg


def puo_modificare(utente: Utente, seduta: Seduta) -> bool:
    return (
        puo_gestire_assemblee(utente) and not seduta.assemblea.conclusa and seduta.chiusa_il is None
    )


def _verifica(utente: Utente, seduta: Seduta) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if seduta.assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")
    if seduta.chiusa_il is not None:
        raise ValidationError("La seduta è chiusa: il programma non si modifica più.")


def _valida(
    seduta: Seduta,
    inizio: datetime.time | None,
    fine: datetime.time | None,
    attivita: str,
    punti: list[PuntoOdG],
) -> datetime.time:
    """Restituisce l'ora di inizio, che dopo i controlli c'è sempre."""
    if inizio is None:
        raise ValidationError("Indica l'ora di inizio.")
    if fine is not None and fine <= inizio:
        raise ValidationError("L'ora di fine deve venire dopo quella di inizio.")
    if not attivita and not punti:
        raise ValidationError("Indica l'attività o almeno un punto dell'ordine del giorno.")
    if any(p.assemblea_id != seduta.assemblea_id for p in punti):
        raise ValidationError("Un punto non è dell'ordine del giorno di questa assemblea.")
    return inizio


@transaction.atomic
def aggiungi_riga(
    seduta: Seduta,
    utente: Utente,
    *,
    inizio: datetime.time | None,
    fine: datetime.time | None = None,
    attivita: str = "",
    punti: Iterable[PuntoOdG] = (),
) -> RigaProgramma:
    _verifica(utente, seduta)
    attivita, punti = attivita.strip(), list(punti)
    inizio = _valida(seduta, inizio, fine, attivita, punti)
    riga = RigaProgramma.objects.create(seduta=seduta, inizio=inizio, fine=fine, attivita=attivita)
    riga.punti.set(punti)
    return riga


@transaction.atomic
def modifica_riga(
    riga: RigaProgramma,
    utente: Utente,
    *,
    inizio: datetime.time | None,
    fine: datetime.time | None = None,
    attivita: str = "",
    punti: Iterable[PuntoOdG] = (),
) -> None:
    _verifica(utente, riga.seduta)
    attivita, punti = attivita.strip(), list(punti)
    inizio = _valida(riga.seduta, inizio, fine, attivita, punti)
    riga.inizio, riga.fine, riga.attivita = inizio, fine, attivita
    riga.save(update_fields=["inizio", "fine", "attivita"])
    riga.punti.set(punti)


@transaction.atomic
def elimina_riga(riga: RigaProgramma, utente: Utente) -> None:
    _verifica(utente, riga.seduta)
    riga.delete()


def seduta_precedente(seduta: Seduta) -> Seduta | None:
    return (
        seduta.assemblea.sedute.filter(convocazione__lt=seduta.convocazione)
        .order_by("-convocazione")
        .first()
    )


@transaction.atomic
def copia_dalla_precedente(seduta: Seduta, utente: Utente) -> int:
    """Copia le righe della convocazione precedente in una seduta ancora senza
    programma (stessa assemblea, quindi stessi punti dell'OdG). Restituisce il
    numero di righe copiate."""
    _verifica(utente, seduta)
    if seduta.programma.exists():
        raise ValidationError("Il programma di questa seduta ha già delle righe.")
    precedente = seduta_precedente(seduta)
    righe = list(precedente.programma.prefetch_related("punti")) if precedente else []
    if not righe:
        raise ValidationError("La convocazione precedente non ha un programma da copiare.")
    for r in righe:
        copia = RigaProgramma.objects.create(
            seduta=seduta, inizio=r.inizio, fine=r.fine, attivita=r.attivita
        )
        copia.punti.set(r.punti.all())
    return len(righe)


def righe(seduta: Seduta) -> list[RigaProgramma]:
    return list(seduta.programma.prefetch_related("punti").order_by("inizio", "pk"))


def in_corso(seduta: Seduta, elenco: list[RigaProgramma], adesso: datetime.datetime) -> set[int]:
    """Righe in corso all'ora `adesso`, solo nel giorno della seduta. Una riga
    senza ora di fine dura fino all'inizio della riga successiva (l'ultima fino
    a fine giornata); con l'ora di fine, fra quella e la riga successiva non è
    in corso nulla. Più righe sovrapposte possono essere in corso insieme."""
    locale = timezone.localtime(adesso)
    if locale.date() != seduta.data:
        return set()
    ora = locale.time()
    risultato = set()
    for i, riga in enumerate(elenco):
        fine = riga.fine
        if fine is None:
            successive = [r.inizio for r in elenco[i + 1 :] if r.inizio > riga.inizio]
            fine = successive[0] if successive else None
        if riga.inizio <= ora and (fine is None or ora < fine):
            risultato.add(riga.pk)
    return risultato


def firma(elenco: list[RigaProgramma]) -> str:
    """Impronta del contenuto del programma: la pagina di chi lo consulta si
    ricarica quando cambia (polling)."""
    testo = "\n".join(
        f"{r.pk}\t{r.inizio:%H:%M}\t{r.fine or ''}\t{r.descrizione}\t"
        + ",".join(str(p) for p in r.punti_ordinati)
        for r in elenco
    )
    return hashlib.sha256(testo.encode()).hexdigest()[:16]


def genera_programma_pdf(seduta: Seduta, utente: Utente) -> bytes:
    from weasyprint import HTML

    if not puo_vedere_odg(utente, seduta.assemblea):
        raise PermissionDenied
    contesto = {
        **contesto_carta_intestata(),
        "assemblea": seduta.assemblea,
        "seduta": seduta,
        "righe": righe(seduta),
    }
    html = render_to_string("assemblee/programma_pdf.html", contesto)
    return HTML(string=html).write_pdf()
