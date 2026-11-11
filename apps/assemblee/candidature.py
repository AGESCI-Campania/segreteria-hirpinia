"""Posizioni al voto e candidature preparate in anticipo (docs/plan_
preparazione_assemblea.md, R1-R2, D3, D4, D6). Unico punto per crearle,
cambiarle e toglierle; le gestiscono ADMIN, SEGRETERIA e RdZ.

- Una posizione ha posti maschili, femminili e indifferenti (D4).
- Una candidatura è un avente diritto dell'elenco (sesso dell'elenco, D6) o
  un nome scritto a mano con il suo sesso, se noto.
- Il controllo sul sesso è un avviso (R2), tranne un caso (D3): un'elezione
  con quote non si apre finché un candidato non ha il sesso
  (`verifica_apribile()`, chiamata da `votazioni.apri_votazione()`)."""

from __future__ import annotations

import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import Utente

from .models import (
    Assemblea,
    AventeDiritto,
    Candidatura,
    PosizioneVoto,
    PuntoOdG,
    Sesso,
)
from .permessi import puo_gestire_assemblee


def _verifica(utente: Utente, assemblea: Assemblea) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")


def _posti(maschili: int, femminili: int, indifferenti: int) -> tuple[int, int, int]:
    posti = (maschili, femminili, indifferenti)
    if any(p is None or p < 0 for p in posti):
        raise ValidationError("I posti non possono essere negativi.")
    if sum(posti) < 1:
        raise ValidationError("Una posizione ha almeno un posto.")
    return posti


def _punto(assemblea: Assemblea, punto: PuntoOdG | None) -> PuntoOdG | None:
    if punto is not None and punto.assemblea_id != assemblea.pk:
        raise ValidationError("Il punto non è dell'ordine del giorno di questa assemblea.")
    return punto


@transaction.atomic
def aggiungi_posizione(
    assemblea: Assemblea,
    utente: Utente,
    *,
    incarico: str,
    posti_maschili: int = 0,
    posti_femminili: int = 0,
    posti_indifferenti: int = 0,
    punto: PuntoOdG | None = None,
) -> PosizioneVoto:
    _verifica(utente, assemblea)
    if not incarico.strip():
        raise ValidationError("Indica l'incarico da eleggere.")
    maschili, femminili, indifferenti = _posti(posti_maschili, posti_femminili, posti_indifferenti)
    return PosizioneVoto.objects.create(
        assemblea=assemblea,
        incarico=incarico.strip(),
        punto=_punto(assemblea, punto),
        posti_maschili=maschili,
        posti_femminili=femminili,
        posti_indifferenti=indifferenti,
    )


@transaction.atomic
def modifica_posizione(
    posizione: PosizioneVoto,
    utente: Utente,
    *,
    incarico: str,
    posti_maschili: int,
    posti_femminili: int,
    posti_indifferenti: int,
    punto: PuntoOdG | None = None,
) -> None:
    """Le votazioni già aperte da questa posizione non cambiano: incarico,
    posti e candidati sono stati copiati all'apertura."""
    _verifica(utente, posizione.assemblea)
    if not incarico.strip():
        raise ValidationError("Indica l'incarico da eleggere.")
    maschili, femminili, indifferenti = _posti(posti_maschili, posti_femminili, posti_indifferenti)
    posizione.incarico = incarico.strip()
    posizione.punto = _punto(posizione.assemblea, punto)
    posizione.posti_maschili = maschili
    posizione.posti_femminili = femminili
    posizione.posti_indifferenti = indifferenti
    posizione.save()


@transaction.atomic
def elimina_posizione(posizione: PosizioneVoto, utente: Utente) -> None:
    """Le votazioni già aperte restano, senza posizione."""
    _verifica(utente, posizione.assemblea)
    posizione.delete()


@transaction.atomic
def aggiungi_candidatura(
    posizione: PosizioneVoto,
    utente: Utente,
    *,
    avente: AventeDiritto | None = None,
    nome: str = "",
    sesso: str = "",
    arrivata_il: datetime.date | None = None,
) -> Candidatura:
    """Un avente diritto, oppure un nome scritto a mano (chi non è
    nell'elenco) con il suo sesso se noto."""
    _verifica(utente, posizione.assemblea)
    if sesso and sesso not in Sesso.values:
        raise ValidationError("Sesso non valido.")
    if avente is not None:
        if avente.assemblea_id != posizione.assemblea_id or avente.eliminato_il is not None:
            raise ValidationError("Il capo non è nell'elenco degli aventi diritto.")
        if posizione.candidature.filter(avente=avente).exists():
            raise ValidationError(f"{avente} è già candidato per questa posizione.")
        # Per un avente vale il sesso dell'elenco: si corregge lì (D6).
        nome, sesso = "", ""
    elif not nome.strip():
        raise ValidationError("Scegli un capo dall'elenco o scrivi il nome del candidato.")
    return Candidatura.objects.create(
        posizione=posizione,
        avente=avente,
        nome=nome.strip(),
        sesso=sesso,
        arrivata_il=arrivata_il,
        inserita_da=utente,
    )


@transaction.atomic
def rimuovi_candidatura(candidatura: Candidatura, utente: Utente) -> None:
    _verifica(utente, candidatura.posizione.assemblea)
    candidatura.delete()


def candidature(posizione: PosizioneVoto):
    return posizione.candidature.select_related("avente", "avente__gruppo").order_by("inserita_il")


def posizioni(assemblea: Assemblea):
    return assemblea.posizioni.select_related("punto").order_by("creata_il")


def _etichetta_sesso(sesso: str, plurale: bool = False) -> str:
    if sesso == Sesso.MASCHILE:
        return "maschili" if plurale else "maschile"
    return "femminili" if plurale else "femminile"


def avvisi(posizione: PosizioneVoto) -> list[str]:
    """Controlli sul sesso e sulle candidature, non bloccanti (R2)."""
    risultato = []
    elenco_candidature = list(candidature(posizione))
    if not elenco_candidature:
        return ["Nessuna candidatura."]
    solo = None
    if posizione.posti_indifferenti == 0:
        if posizione.posti_femminili == 0:
            solo = Sesso.MASCHILE
        elif posizione.posti_maschili == 0:
            solo = Sesso.FEMMINILE
    for candidatura in elenco_candidature:
        sesso = candidatura.sesso_effettivo
        if candidatura.avente is not None and candidatura.avente.eliminato_il is not None:
            risultato.append(f"{candidatura}: non è più nell'elenco degli aventi diritto.")
        if not sesso:
            if posizione.con_quote:
                risultato.append(
                    f"{candidatura}: sesso non noto, va indicato prima di aprire l'elezione."
                )
            else:
                risultato.append(f"{candidatura}: sesso non noto.")
        elif solo and sesso != solo:
            risultato.append(
                f"{candidatura}: candidatura {_etichetta_sesso(sesso)} per posti solo "
                f"{_etichetta_sesso(solo, plurale=True)}."
            )
    for sesso, posti in (
        (Sesso.MASCHILE, posizione.posti_maschili),
        (Sesso.FEMMINILE, posizione.posti_femminili),
    ):
        candidati = sum(1 for c in elenco_candidature if c.sesso_effettivo == sesso)
        if posti and candidati < posti:
            risultato.append(
                f"Posti {_etichetta_sesso(sesso, plurale=True)}: {posti}, candidature "
                f"{_etichetta_sesso(sesso, plurale=True)}: {candidati}."
            )
    return risultato


def verifica_apribile(posizione: PosizioneVoto) -> list[Candidatura]:
    """Le candidature con cui si apre l'elezione. Bloccante solo ciò che non
    permette di votare (D3): nessuna candidatura, o un candidato senza sesso
    in un'elezione con quote. Le candidature di chi è uscito dall'elenco non
    entrano."""
    validi = [
        c for c in candidature(posizione) if c.avente is None or c.avente.eliminato_il is None
    ]
    if not validi:
        raise ValidationError("Per questa posizione non ci sono candidature.")
    if posizione.con_quote:
        senza_sesso = [str(c) for c in validi if not c.sesso_effettivo]
        if senza_sesso:
            raise ValidationError(
                "Elezione con posti maschili e femminili: indica il sesso di "
                + ", ".join(senza_sesso)
                + " prima di aprirla."
            )
    return validi
