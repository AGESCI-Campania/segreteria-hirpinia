"""Quorum dell'assemblea (D-70, regolamento art. 4): unico punto del calcolo.

`meta_piu_uno()` è la sola definizione di "metà + 1" del modulo: la usano il
quorum costitutivo qui e le soglie delle votazioni."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet

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


def verifica_senza_quorum(seduta: Seduta) -> Appello | None:
    """La verifica che non ha confermato il quorum costitutivo e con cui la
    seduta è stata chiusa (art. 4 c.5-6), se c'è."""
    return (
        seduta.appelli.filter(
            tipo=TipoAppello.VERIFICA, chiuso_il__isnull=False, quorum_raggiunto=False
        )
        .order_by("-numero")
        .first()
    )


def verifica_in_corso(seduta: Seduta) -> Appello | None:
    """La verifica del quorum aperta e non ancora chiusa, se c'è."""
    return seduta.appelli.filter(tipo=TipoAppello.VERIFICA, chiuso_il__isnull=True).first()


def presenti(seduta: Seduta) -> QuerySet[AventeDiritto]:
    """Presenti che contano ora per quorum e votazioni: quelli dell'appello
    effettivo (art. 4 c.6: durante una verifica valgono ancora i precedenti)."""
    appello = appello_effettivo(seduta)
    if appello is None:
        return AventeDiritto.objects.none()
    return presenti_nell_appello(appello)


def presenti_nell_appello(appello: Appello) -> QuerySet[AventeDiritto]:
    """Aventi diritto ancora nell'elenco registrati di persona in `appello`,
    più gli AE che hanno delegato uno di loro (art. 4 c.2: "registrati
    personalmente o per delega"). Chi è sia presente sia delegante conta una
    volta sola."""
    seduta = appello.seduta
    elenco = seduta.assemblea.aventi_diritto.nell_elenco()
    di_persona = elenco.filter(presenze__appello=appello)
    deleganti = seduta.deleghe.filter(delegato__in=di_persona).values("delegante_id")
    return elenco.filter(Q(pk__in=di_persona.values("pk")) | Q(pk__in=deleganti))


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


def stato_quorum(seduta: Seduta, appello: Appello | None = None) -> StatoQuorum:
    """Quorum costitutivo: metà degli aventi diritto + 1 (art. 4 c.1), sui
    presenti dell'appello effettivo o di `appello` (es. una verifica in corso)."""
    aventi = seduta.assemblea.aventi_diritto.nell_elenco().count()
    qs = presenti_nell_appello(appello) if appello is not None else presenti(seduta)
    totale = qs.count()
    app = qs.filter(vota_in_app=True).count()
    return StatoQuorum(
        aventi_diritto=aventi,
        presenti=totale,
        presenti_app=app,
        presenti_carta=totale - app,
        soglia=None if seduta.senza_quorum else meta_piu_uno(aventi),
    )


# --- Presenze durante le votazioni -------------------------------------------------
#
# Chi arriva mentre una votazione è aperta (risultati non ancora registrati)
# vota ed entra nei presenti di quella votazione, cioè nella base della
# maggioranza; togliere una presenza o revocare una delega a votazione aperta
# non si può, cambierebbe la base già usata (decisione del 2026-11-11).


def votazioni_in_corso(seduta: Seduta):
    return seduta.votazioni.filter(chiusa_il__isnull=True)


def aggiorna_presenti_votazioni(seduta: Seduta) -> None:
    """Dopo un arrivo (presenza o delega): i presenti delle votazioni non
    ancora chiuse crescono fino ai presenti attuali, mai diminuiscono."""
    presenti = stato_quorum(seduta).presenti
    votazioni_in_corso(seduta).filter(presenti__lt=presenti).update(presenti=presenti)


def verifica_nessuna_votazione_in_corso(seduta: Seduta, cosa: str) -> None:
    if votazioni_in_corso(seduta).exists():
        raise ValidationError(
            f"C'è una votazione aperta: {cosa} non si può finché non sono registrati i "
            "risultati (cambierebbe la base della maggioranza)."
        )
