"""Effetto sul contributo della disattivazione di un gruppo (D-24/A-6/A-10).
Agganciata via segnale `post_save` su `StatoGruppoAnno`
(`apps/contributi/apps.py::ready()`), stesso principio di
`apps/contributi/trasferimenti.py` per `TrasferimentoCapo`: `contributi`
dipende già da `organizzazione` (Gruppo, iban), mai il contrario, quindi il
segnale evita di far chiamare `contributi` direttamente da
`apps.organizzazione.gruppi::disattiva_gruppo` restando nella stessa
transazione (post_save è sincrono)."""

from __future__ import annotations

from django.utils import timezone

from apps.anagrafica.models import TrasferimentoCapo
from apps.organizzazione.models import Gruppo, StatoGruppoAnno

from .models import Campagna, Partecipazione, StatoCampagna, StatoPartecipazione


def su_disattivazione_gruppo(sender, instance: StatoGruppoAnno, created: bool, **kwargs) -> None:
    if not created or instance.attivo:
        return
    respingi_per_disattivazione(instance)


def conta_effetti_disattivazione(gruppo: Gruppo, anno_scout: int) -> dict[str, int]:
    """Anteprima a sola lettura per la conferma esplicita richiesta da D-24
    ("elenca quante partecipazioni verranno respinte e quante ri-attribuite
    altrove"). Vive in `contributi`, non in `organizzazione`: entrambi i
    conteggi leggono `Partecipazione`/`TrasferimentoCapo`, concetti che
    `organizzazione` non conosce (dipendenza a senso unico, §4)."""
    campagna = Campagna.objects.filter(anno=anno_scout).first()
    if campagna is None:
        return {"verranno_respinte": 0, "gia_riattribuite_altrove": 0}

    verranno_respinte = (
        Partecipazione.objects.filter(campagna=campagna, gruppo=gruppo)
        .exclude(stato=StatoPartecipazione.RESPINTA)
        .count()
    )
    capi_trasferiti = TrasferimentoCapo.objects.filter(
        gruppo_origine=gruppo, anno_scout=anno_scout
    ).values_list("capo_id", flat=True)
    gia_riattribuite_altrove = (
        Partecipazione.objects.filter(campagna=campagna, capo_id__in=capi_trasferiti)
        .exclude(gruppo=gruppo)
        .count()
    )
    return {
        "verranno_respinte": verranno_respinte,
        "gia_riattribuite_altrove": gia_riattribuite_altrove,
    }


def respingi_per_disattivazione(stato: StatoGruppoAnno) -> list[Partecipazione]:
    """A-6: un gruppo disattivato non ha diritto ad alcun contributo per
    l'anno, nemmeno per il periodo in cui era attivo — anche le
    partecipazioni già APPROVATA passano a RESPINTA. Tocca solo le
    partecipazioni ancora attribuite al gruppo: quelle dei capi già
    ri-attribuiti altrove (D-29) hanno un `gruppo` diverso e non vengono
    toccate, rispettando così l'ordine richiesto da D-24 senza doverlo
    imporre esplicitamente. A campagna LIQUIDATA non si fa nulla (A-10): il
    bonifico è già partito."""
    campagna = Campagna.objects.filter(anno=stato.anno_scout).first()
    if campagna is None or campagna.stato == StatoCampagna.LIQUIDATA:
        return []

    partecipazioni = Partecipazione.objects.filter(campagna=campagna, gruppo=stato.gruppo).exclude(
        stato=StatoPartecipazione.RESPINTA
    )

    respinte = []
    ora = timezone.now()
    for partecipazione in partecipazioni:
        partecipazione.respingi()
        partecipazione.motivazione_respingimento = "Gruppo non più attivo"
        partecipazione.valutata_da = stato.disposto_da
        partecipazione.data_valutazione = ora
        partecipazione.full_clean(exclude=["stato"])
        partecipazione.save()
        respinte.append(partecipazione)
    return respinte
