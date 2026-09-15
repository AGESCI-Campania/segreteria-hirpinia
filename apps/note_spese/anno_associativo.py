"""Derivazione dell'anno associativo da una data (D-41): l'anno associativo
2026/2027 (1/10/2026 - 30/9/2027) si identifica con il solo 2027, coerente
con `AnnoAssociativo.__str__()` in `apps.organizzazione.models`."""

from __future__ import annotations

import datetime

MESE_INIZIO_ANNO_ASSOCIATIVO = 10


def anno_associativo_per_data(data: datetime.date) -> int:
    if data.month >= MESE_INIZIO_ANNO_ASSOCIATIVO:
        return data.year + 1
    return data.year


def calcola_anno_spesa(date_righe: list[datetime.date]) -> int | None:
    """D-41: l'anno associativo di spesa deriva dalle date delle righe.
    Inferenza dichiarata (non specificata nei requisiti): si usa la data più
    antica fra le righe, cioè l'inizio dell'occasione a cui la nota si
    riferisce, non la più recente né una moda — coerente con D-44 ("più
    righe eterogenee riferite alla stessa occasione"). Righe la cui data
    attraversa il confine dell'anno associativo (30 settembre) restano un
    caso limite non affrontato esplicitamente dai requisiti."""

    if not date_righe:
        return None
    return anno_associativo_per_data(min(date_righe))
