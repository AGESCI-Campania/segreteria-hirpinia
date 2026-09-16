"""Calcolo dell'importo di una riga auto (D-52/D-53) e congelamento della
distanza (D-54). Le due sottocategorie hanno regole diverse, distinte
**sempre** da `CategoriaSpesa.sottotipo_chilometrico` (D-53), mai dal nome
della categoria (anagrafica editabile).

**Inferenza dichiarata sull'arrotondamento**: D-52 dice solo "aritmetica
Decimal", senza specificare il modo di arrotondamento (a differenza di D-10
per i contributi, che impone `ROUND_DOWN`). Uso `ROUND_HALF_UP` (arrotondamento
ordinario) ai 2 decimali finali, non il default di modulo di `Decimal`
(`ROUND_HALF_EVEN`, meno intuitivo per un importo in euro)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from .calcolo_km import SOGLIA_KM, fascia_per, tariffa_km
from .models import FasciaTariffaChilometrica, RigaSpesa, SottotipoChilometrico
from .routing import distanza_km_tra_localita

DUE_DECIMALI = Decimal("0.01")


def _numero_occupanti(riga: RigaSpesa) -> int:
    """D-52: la soglia "3 o più passeggeri" è **conducente incluso** — chi
    guida non ha una riga propria in `RigaSpesaPasseggero` (quelle righe
    registrano gli *altri* occupanti, per il controllo anti-doppione di
    D-57), quindi il conteggio della fascia è `passeggeri.count() + 1`."""
    return riga.passeggeri.count() + 1


def _distanza_effettiva(riga: RigaSpesa) -> Decimal:
    distanza = (
        riga.distanza_corretta_km if riga.distanza_corretta_km is not None else riga.distanza_km
    )
    if distanza is None:
        raise ValidationError("La distanza non è ancora stata calcolata su questa riga.")
    return distanza


def _congela_distanza(riga: RigaSpesa) -> Decimal:
    """D-54: calcola e persiste la distanza una sola volta — se è già
    congelata (`distanza_km` non nullo) non richiama il backend di routing,
    così una nota già valutata non cambia se il router restituisce in futuro
    un valore diverso."""
    if riga.distanza_km is not None:
        return _distanza_effettiva(riga)
    partenza, arrivo = riga.localita_partenza, riga.localita_arrivo
    if partenza is None or arrivo is None:
        raise ValidationError(
            "Servono partenza e arrivo per calcolare la distanza di una riga auto."
        )
    distanza, nome_backend = distanza_km_tra_localita(partenza, arrivo)
    riga.distanza_km = distanza
    riga.distanza_backend = nome_backend
    riga.distanza_calcolata_il = timezone.now()
    return distanza


def _importo(distanza: Decimal, tariffa: Decimal) -> Decimal:
    return (distanza * tariffa).quantize(DUE_DECIMALI, rounding=ROUND_HALF_UP)


def calcola_importo_altri_spostamenti(riga: RigaSpesa) -> Decimal:
    """D-53: calcolo per singola riga, passeggeri ininfluenti sulla
    tariffa — la fascia `TRE_O_PIU` non si applica mai qui, solo la soglia
    dei 200 km sulla distanza della singola riga."""
    if riga.categoria.sottotipo_chilometrico != SottotipoChilometrico.ALTRO:
        raise ValidationError("La riga non è di categoria 'Auto (altri spostamenti)'.")
    distanza = _congela_distanza(riga)
    fascia = (
        FasciaTariffaChilometrica.BREVE
        if distanza <= SOGLIA_KM
        else FasciaTariffaChilometrica.LUNGA
    )
    tariffa = tariffa_km(fascia, riga.data)
    riga.importo = _importo(distanza, tariffa)
    return riga.importo


def calcola_importo_andata_ritorno(righe: list[RigaSpesa]) -> None:
    """D-53: aggrega le righe 'Auto (andata e ritorno)' della stessa nota
    (al più due — un vincolo di interfaccia, la seconda si crea con
    "Duplica" — non impongo qui il limite, aggrego semplicemente quelle
    passate). La fascia è comune a tutte: determinata dal numero di
    occupanti del viaggio più lungo (a parità di distanza, il maggiore) e
    dalla distanza **totale** andata+ritorno. La tariffa applicata a
    ciascuna riga resta invece quella vigente alla **sua** data (coerente
    con la decisione generale su D-52), non una data unica per il viaggio."""
    if not righe:
        return
    if any(
        r.categoria.sottotipo_chilometrico != SottotipoChilometrico.ANDATA_RITORNO for r in righe
    ):
        raise ValidationError(
            "Tutte le righe devono essere di categoria 'Auto (andata e ritorno)'."
        )

    for riga in righe:
        _congela_distanza(riga)

    km_totali = sum((_distanza_effettiva(r) for r in righe), Decimal("0"))
    km_massimo = max(_distanza_effettiva(r) for r in righe)
    righe_piu_lunghe = [r for r in righe if _distanza_effettiva(r) == km_massimo]
    occupanti_fascia = max(_numero_occupanti(r) for r in righe_piu_lunghe)
    fascia = fascia_per(occupanti_fascia, km_totali)

    for riga in righe:
        tariffa = tariffa_km(fascia, riga.data)
        riga.importo = _importo(_distanza_effettiva(riga), tariffa)


def calcola_importo_riga_auto(riga: RigaSpesa) -> None:
    """Punto d'ingresso unico (D-69): dispatcha in base a
    `sottotipo_chilometrico`, mai richiamato direttamente dalle view per una
    sola sottocategoria — evita che la logica di aggregazione D-53 venga
    bypassata per errore."""
    sottotipo = riga.categoria.sottotipo_chilometrico
    if sottotipo == SottotipoChilometrico.ALTRO:
        calcola_importo_altri_spostamenti(riga)
        riga.save()
    elif sottotipo == SottotipoChilometrico.ANDATA_RITORNO:
        righe_gruppo = list(
            riga.nota.righe.filter(
                categoria__sottotipo_chilometrico=SottotipoChilometrico.ANDATA_RITORNO
            )
        )
        if riga not in righe_gruppo:
            righe_gruppo.append(riga)
        calcola_importo_andata_ritorno(righe_gruppo)
        for r in righe_gruppo:
            r.save()
    else:
        raise ValidationError("La categoria non è di tipo chilometrico riconosciuto (D-53).")
