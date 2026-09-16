"""Controllo anti-doppione delle righe auto (D-57): **segnalazione, non
blocco** — due capi possono legittimamente usare la stessa auto in giorni
diversi, quindi queste funzioni restituiscono sempre e solo elenchi di
sospetti da mostrare in verifica, mai un'eccezione che impedisce di
procedere.

**Inferenze dichiarate** (non specificate testualmente da D-57):
- "Stessa tratta" è letta come stessa coppia partenza→arrivo nella stessa
  direzione, non la stessa rotta indipendentemente dal verso.
- Per una riga "Auto (andata e ritorno)", l'intervallo temporale usato per
  la sovrapposizione di targa è quello dell'intero viaggio (andata+ritorno
  della stessa nota, stessa targa), non il solo giorno della riga: l'auto è
  indisponibile per tutto il periodo, non solo nei due giorni di
  partenza/ritorno. Per "Auto (altri spostamenti)" resta il solo giorno
  della riga."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from .models import RigaSpesa, RigaSpesaPasseggero, SottotipoChilometrico


@dataclass(frozen=True)
class SegnalazionePasseggero:
    riga: RigaSpesa
    passeggero: RigaSpesaPasseggero
    riga_del_passeggero: RigaSpesa


@dataclass(frozen=True)
class SegnalazioneTarga:
    riga: RigaSpesa
    altra_riga: RigaSpesa


def segnalazioni_passeggero_con_propria_riga(riga: RigaSpesa) -> list[SegnalazionePasseggero]:
    """D-57, prima condizione: un passeggero (capo strutturato, non "Altro"
    a nome libero — quello non è verificabile) che ha presentato a sua
    volta una riga auto per la stessa tratta e lo stesso evento."""
    if riga.localita_partenza_id is None or riga.localita_arrivo_id is None:
        return []
    evento_id = riga.nota.evento_id
    segnalazioni: list[SegnalazionePasseggero] = []
    for passeggero in riga.passeggeri.exclude(capo__isnull=True):
        altre_righe = RigaSpesa.objects.filter(
            nota__evento_id=evento_id,
            nota__beneficiario_id=passeggero.capo_id,
            localita_partenza_id=riga.localita_partenza_id,
            localita_arrivo_id=riga.localita_arrivo_id,
        ).exclude(nota_id=riga.nota_id)
        for riga_del_passeggero in altre_righe:
            segnalazioni.append(SegnalazionePasseggero(riga, passeggero, riga_del_passeggero))
    return segnalazioni


def _intervallo_riga(riga: RigaSpesa) -> tuple[datetime.date, datetime.date]:
    if riga.categoria.sottotipo_chilometrico == SottotipoChilometrico.ANDATA_RITORNO and riga.targa:
        date = list(
            riga.nota.righe.filter(
                categoria__sottotipo_chilometrico=SottotipoChilometrico.ANDATA_RITORNO,
                targa=riga.targa,
            ).values_list("data", flat=True)
        )
        if riga.data not in date:
            date.append(riga.data)
        return min(date), max(date)
    return riga.data, riga.data


def segnalazioni_targa_sovrapposta(riga: RigaSpesa) -> list[SegnalazioneTarga]:
    """D-57, seconda condizione: la stessa targa in richieste (di note
    diverse) sovrapposte nello stesso intervallo temporale."""
    if not riga.targa:
        return []
    inizio, fine = _intervallo_riga(riga)
    segnalazioni: list[SegnalazioneTarga] = []
    for altra in RigaSpesa.objects.filter(targa=riga.targa).exclude(nota_id=riga.nota_id):
        altro_inizio, altra_fine = _intervallo_riga(altra)
        if inizio <= altra_fine and altro_inizio <= fine:
            segnalazioni.append(SegnalazioneTarga(riga, altra))
    return segnalazioni
