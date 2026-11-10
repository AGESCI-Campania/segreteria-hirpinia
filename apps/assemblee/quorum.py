"""Quorum dell'assemblea (D-70, regolamento art. 4): unico punto del calcolo.

`meta_piu_uno()` è la sola definizione di "metà + 1" del modulo: la usano il
quorum costitutivo qui e le soglie delle votazioni."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import QuerySet

from .models import Appello, AventeDiritto, Seduta, TipoAppello


def meta_piu_uno(n: int) -> int:
    return n // 2 + 1


def appello_attivo(seduta: Seduta) -> Appello | None:
    """L'appello in cui si registrano le nuove presenze: sempre l'ultimo."""
    return seduta.appelli.order_by("-numero").first()


def appello_effettivo(seduta: Seduta) -> Appello | None:
    """L'appello su cui si contano i presenti: l'ingresso, o l'ultima verifica
    del quorum già chiusa (art. 4 c.5-6)."""
    validi = seduta.appelli.filter(tipo=TipoAppello.INGRESSO) | seduta.appelli.filter(
        tipo=TipoAppello.VERIFICA, chiuso_il__isnull=False
    )
    return validi.order_by("-numero").first()


def presenti(seduta: Seduta) -> QuerySet[AventeDiritto]:
    """Aventi diritto presenti per il quorum, ancora nell'elenco."""
    appello = appello_effettivo(seduta)
    if appello is None:
        return AventeDiritto.objects.none()
    return seduta.assemblea.aventi_diritto.nell_elenco().filter(presenze__appello=appello)


@dataclass(frozen=True)
class StatoQuorum:
    aventi_diritto: int
    presenti: int
    presenti_app: int
    presenti_carta: int
    # None in terza convocazione: nessun quorum costitutivo (art. 4 c.3).
    soglia: int | None

    @property
    def raggiunto(self) -> bool:
        return self.soglia is None or self.presenti >= self.soglia

    @property
    def mancanti(self) -> int:
        if self.soglia is None:
            return 0
        return max(self.soglia - self.presenti, 0)


def stato_quorum(seduta: Seduta) -> StatoQuorum:
    """Quorum costitutivo: metà degli aventi diritto + 1 (art. 4 c.1)."""
    aventi = seduta.assemblea.aventi_diritto.nell_elenco().count()
    qs = presenti(seduta)
    totale = qs.count()
    app = qs.filter(vota_in_app=True).count()
    return StatoQuorum(
        aventi_diritto=aventi,
        presenti=totale,
        presenti_app=app,
        presenti_carta=totale - app,
        soglia=None if seduta.senza_quorum else meta_piu_uno(aventi),
    )
