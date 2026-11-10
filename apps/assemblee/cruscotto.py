"""Dati per cruscotto, vista proiettore ed elenco di abilitazione in app (D-70).

Nessuna regola nuova: presenti e quorum vengono da quorum.py, le deleghe dal
modello. Qui solo la forma dei dati per le pagine aggiornate in tempo reale
(polling ogni 3 secondi, nessuna infrastruttura nuova: D-17)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.db.models import Max
from django.utils import timezone

from .models import AventeDiritto, Presenza, Seduta
from .quorum import appello_effettivo, presenti, stato_quorum, verifica_in_corso
from .votazioni import soglie_correnti

INTERVALLO_AGGIORNAMENTO_MS = 3000


@dataclass(frozen=True)
class Presente:
    avente: AventeDiritto
    arrivato_il: datetime.datetime | None
    # Per un AE delegante: chi lo rappresenta (presente di persona).
    delegato: AventeDiritto | None


def elenco_presenti(seduta: Seduta) -> list[Presente]:
    """I presenti che contano ora, dall'ultimo arrivato. Per un AE delegante
    l'ora è quella in cui è arrivato il delegato o è stata registrata la
    delega, la più recente delle due."""
    appello = appello_effettivo(seduta)
    if appello is None:
        return []
    aventi = list(presenti(seduta).select_related("gruppo", "gruppo_origine"))
    arrivi = dict(
        Presenza.objects.filter(appello=appello, avente__in=aventi)
        .values("avente_id")
        .annotate(ora=Max("registrata_il"))
        .values_list("avente_id", "ora")
    )
    deleghe = {d.delegante_id: d for d in seduta.deleghe.select_related("delegato")}
    risultato = []
    for avente in aventi:
        delega = deleghe.get(avente.pk)
        ora = arrivi.get(avente.pk)
        delegato = None
        if ora is None and delega is not None:
            delegato = delega.delegato
            ora = max(filter(None, [delega.registrata_il, arrivi.get(delega.delegato_id)]))
        elif delega is not None:
            delegato = delega.delegato
        risultato.append(Presente(avente=avente, arrivato_il=ora, delegato=delegato))
    minimo = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    risultato.sort(key=lambda p: p.arrivato_il or minimo, reverse=True)
    return risultato


def stato_seduta(seduta: Seduta, *, con_elenco: bool = False) -> dict:
    """Dati del cruscotto in forma serializzabile. L'elenco nominativo solo se
    richiesto: la vista proiettore mostra soltanto numeri."""
    stato = stato_quorum(seduta)
    verifica = verifica_in_corso(seduta)
    dati: dict = {
        "aggiornato_il": timezone.localtime().strftime("%H:%M:%S"),
        "seduta": {
            "aperta": seduta.aperta,
            "costituita": seduta.costituita,
            "convocazione": seduta.get_convocazione_display(),
        },
        "aventi_diritto": stato.aventi_diritto,
        "presenti": stato.presenti,
        "presenti_app": stato.presenti_app,
        "presenti_carta": stato.presenti_carta,
        "soglia": stato.soglia,
        "raggiunto": stato.raggiunto,
        "mancanti": stato.mancanti,
        "verifica": None,
        "soglie": soglie_correnti(stato.presenti, stato.aventi_diritto),
    }
    if verifica is not None:
        in_verifica = stato_quorum(seduta, verifica)
        dati["verifica"] = {
            "richiedente": verifica.get_richiedente_display(),
            "presenti": in_verifica.presenti,
            "soglia": in_verifica.soglia,
            "raggiunto": in_verifica.raggiunto,
        }
    if con_elenco:
        dati["elenco"] = [
            {
                "cognome": p.avente.cognome,
                "nome": p.avente.nome,
                "gruppo": p.avente.gruppo.nome,
                "voto": "App" if p.avente.vota_in_app else "Carta",
                "ora": timezone.localtime(p.arrivato_il).strftime("%H:%M") if p.arrivato_il else "",
                "delegato": (
                    f"{p.delegato.cognome} {p.delegato.nome}"
                    if p.delegato is not None and p.avente.pk != p.delegato.pk
                    else ""
                ),
            }
            for p in elenco_presenti(seduta)
        ]
    return dati


def presenti_in_app(seduta: Seduta) -> list[Presente]:
    """Per chi abilita i votanti sull'app nazionale: solo i presenti che votano
    in app, dall'ultimo arrivato."""
    return [p for p in elenco_presenti(seduta) if p.avente.vota_in_app]
