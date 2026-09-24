"""Servizio unico di esportazione (D-68, F8): i quattro riepiloghi sono
varianti dello stesso oggetto — note liquidate filtrate e aggregate
diversamente — un solo servizio con raggruppamento selezionabile, non
quattro funzioni separate. Stessa queryset di base di `note_visibili()`
(D-66): i totali non divergono da un report all'altro. Tutti i riepiloghi
sull'anno associativo di **liquidazione** (`anno_contabilizzazione`, D-41),
non l'anno di spesa."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from django.db import models
from django.db.models import QuerySet, Sum

from apps.accounts.models import Utente

from .categorie import mappa_categoria_principale
from .models import CategoriaSpesa, NotaSpese, StatoNota
from .visibilita import note_visibili


class RaggruppamentoEsportazione(models.TextChoices):
    CENTRO_COSTO = "CENTRO_COSTO", "Centro di costo"
    EVENTO = "EVENTO", "Evento"
    CAPO = "CAPO", "Capo"
    NESSUNO = "NESSUNO", "Riepilogo per il bilancio"


@dataclass(frozen=True)
class RisultatoEsportazione:
    """Tabella già pronta per csv/xlsx: intestazioni fisse per i tre
    raggruppamenti aggregati, dinamiche (una colonna per categoria
    principale realmente presente nell'anno) per il riepilogo di bilancio
    — la view non conosce la differenza, scrive semplicemente questa
    tabella."""

    intestazioni: list[str]
    righe: list[list[str]]


def _note_liquidate(utente: Utente, anno_liquidazione: int) -> QuerySet[NotaSpese]:
    return note_visibili(utente).filter(
        stato=StatoNota.LIQUIDATA, anno_contabilizzazione=anno_liquidazione
    )


def _importo(valore: Decimal | None) -> str:
    return str(valore) if valore is not None else "0"


def _per_centro_costo(note: QuerySet[NotaSpese]) -> RisultatoEsportazione:
    totali = (
        note.values("centro_costo__nome")
        .annotate(totale=Sum("righe__importo"))
        .order_by("centro_costo__nome")
    )
    righe = [
        # Un centro_costo nullo è un'imputazione mancante su una nota
        # liquidata (possibile: liquida() non la richiede) — mostrata
        # esplicitamente, mai scartata: altrimenti l'importo sparirebbe
        # dal riepilogo di bilancio senza traccia.
        [riga["centro_costo__nome"] or "Non imputato", _importo(riga["totale"])]
        for riga in totali
    ]
    return RisultatoEsportazione(intestazioni=["Centro di costo", "Totale"], righe=righe)


def _per_evento(note: QuerySet[NotaSpese]) -> RisultatoEsportazione:
    totali = (
        note.values("evento__nome").annotate(totale=Sum("righe__importo")).order_by("evento__nome")
    )
    righe = [[riga["evento__nome"], _importo(riga["totale"])] for riga in totali]
    return RisultatoEsportazione(intestazioni=["Evento", "Totale"], righe=righe)


def _per_capo(note: QuerySet[NotaSpese]) -> RisultatoEsportazione:
    totali = (
        note.values("beneficiario_id", "beneficiario__nome", "beneficiario__cognome")
        .annotate(totale=Sum("righe__importo"))
        .order_by("beneficiario__cognome", "beneficiario__nome")
    )
    righe = [
        [
            f"{riga['beneficiario__cognome']} {riga['beneficiario__nome']} ({riga['beneficiario_id']})",
            _importo(riga["totale"]),
        ]
        for riga in totali
    ]
    return RisultatoEsportazione(intestazioni=["Capo", "Totale"], righe=righe)


def _bilancio(note: QuerySet[NotaSpese]) -> RisultatoEsportazione:
    """Una riga per nota (D-68). Le colonne di categoria si generano dalle
    categorie principali **realmente presenti** in questo lotto di note, non
    da tutte quelle anagrafiche esistenti oggi: coerente con "il file può
    avere colonne diverse in anni diversi" — una categoria mai usata
    nell'anno non deve comparire, una usata ma oggi disattivata non deve
    sparire.

    **Inferenza dichiarata**: la colonna "Data pagamento" usa
    `NotaSpese.data_pagamento`, che nessun percorso valorizza ancora (gap
    già segnalato in `docs/TODO.md`) — resterà vuota finché quel gap non
    è colmato, non è un difetto di questa funzione."""
    elenco_note = list(
        note.select_related("beneficiario", "evento").prefetch_related("righe__categoria")
    )
    mappa_categoria = mappa_categoria_principale()

    principali_usate: dict[int, CategoriaSpesa] = {}
    per_nota: list[tuple[NotaSpese, dict[int, Decimal], Decimal]] = []
    for nota in elenco_note:
        per_categoria: dict[int, Decimal] = {}
        totale = Decimal("0")
        for riga in nota.righe.all():
            principale = mappa_categoria[riga.categoria_id]
            principali_usate[principale.pk] = principale
            importo = riga.importo or Decimal("0")
            per_categoria[principale.pk] = per_categoria.get(principale.pk, Decimal("0")) + importo
            totale += importo
        per_nota.append((nota, per_categoria, totale))

    colonne_categoria = sorted(principali_usate.values(), key=lambda c: c.nome)
    intestazioni = [
        "Numero",
        "Data pagamento",
        "Evento",
        "Capo",
        *[c.nome for c in colonne_categoria],
        "Totale",
    ]
    righe = []
    for nota, per_categoria, totale in per_nota:
        righe.append(
            [
                nota.numero or "",
                nota.data_pagamento.isoformat() if nota.data_pagamento else "",
                str(nota.evento),
                str(nota.beneficiario),
                *[_importo(per_categoria.get(c.pk)) for c in colonne_categoria],
                _importo(totale),
            ]
        )
    return RisultatoEsportazione(intestazioni=intestazioni, righe=righe)


_FUNZIONI_PER_RAGGRUPPAMENTO: dict[str, Callable[[QuerySet[NotaSpese]], RisultatoEsportazione]] = {
    RaggruppamentoEsportazione.CENTRO_COSTO: _per_centro_costo,
    RaggruppamentoEsportazione.EVENTO: _per_evento,
    RaggruppamentoEsportazione.CAPO: _per_capo,
    RaggruppamentoEsportazione.NESSUNO: _bilancio,
}


def genera_esportazione(
    utente: Utente, *, anno_liquidazione: int, raggruppamento: str
) -> RisultatoEsportazione:
    note = _note_liquidate(utente, anno_liquidazione)
    funzione = _FUNZIONI_PER_RAGGRUPPAMENTO[raggruppamento]
    return funzione(note)
