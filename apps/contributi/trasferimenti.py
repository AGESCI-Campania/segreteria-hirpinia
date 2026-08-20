"""Riattribuzione delle partecipazioni ai trasferimenti (D-29). Agganciata via
segnale `post_save` su `TrasferimentoCapo` (apps/contributi/apps.py::ready()),
non da un import diretto in `apps.anagrafica.importazione`: `contributi`
dipende da `anagrafica`, non il contrario (§4), e il segnale evita di
introdurre quella dipendenza inversa pur restando nella stessa transazione
dell'import CSV che rileva il trasferimento (post_save è sincrono)."""

from __future__ import annotations

from apps.anagrafica.models import TrasferimentoCapo

from .models import Partecipazione, StatoCampagna


def su_trasferimento_capo(sender, instance: TrasferimentoCapo, created: bool, **kwargs) -> None:
    if not created:
        return
    riattribuisci_partecipazioni(instance)


def riattribuisci_partecipazioni(trasferimento: TrasferimentoCapo) -> list[Partecipazione]:
    """D-29: il contributo segue il capo, sposta il destinatario non
    l'importo. A campagna LIQUIDATA non si ri-attribuisce più nulla (A-10):
    il bonifico è già partito."""
    interessate = list(
        Partecipazione.objects.filter(
            capo_id=trasferimento.capo_id,
            gruppo_id=trasferimento.gruppo_origine_id,
        ).exclude(campagna__stato=StatoCampagna.LIQUIDATA)
    )
    for partecipazione in interessate:
        partecipazione.gruppo = trasferimento.gruppo_destino
        partecipazione.save(update_fields=["gruppo"])
    return interessate
