"""Parser del CSV "Ricerca Soci" di Buona Caccia (§6.1 del documento di
progettazione).

Trappole del formato, verificate su un campione reale (187 righe, 81 colonne):
prima riga `sep=,` da saltare, encoding UTF-8 con BOM, valori avvolti in
`="valore"` (le date no), virgola finale su ogni riga (81 intestazioni contro
82 campi: `csv.DictReader` gestisce l'eccedenza in `restkey` senza slittamento
di colonne, mai pandas senza `index_col=False`).

API pubblica:
    parse_csv(source) -> RisultatoParsing
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO, TextIO

ERRORE = "errore"
AVVISO = "avviso"

_RE_WRAP = re.compile(r'^="(.*)"$')
_RE_ORDINALE = re.compile(r"^E\d{4}$")

# Valori osservati sul campione: non un vocabolario chiuso documentato, un
# valore diverso è un avviso non bloccante, non un errore (§6.1).
_STATUS_SOCIO_NOTI = {"RINNOVO ADESIONE", "NUOVA ADESIONE"}


@dataclass(frozen=True)
class AnomaliaRiga:
    numero_riga: int
    livello: str
    campo: str
    dettaglio: str
    codice_socio: str = ""


@dataclass(frozen=True)
class RigaBuonaCaccia:
    numero_riga: int
    codice_socio: str
    nome: str
    cognome: str
    sesso: str
    data_nascita: date | None
    comune_nascita: str
    codice_fiscale: str
    nazionalita: str
    indirizzo: str
    civico: str
    comune_residenza: str
    provincia_residenza: str
    cap: str
    email: str
    cellulare: str
    professione: str
    livello_foca: int | None
    ingresso_coca: str
    comunita_socio: str
    status_socio: str
    ordinale: str
    gruppo_nome: str
    email_gruppo: str
    indirizzo_gruppo: str
    civico_gruppo: str
    cap_gruppo: str
    comune_gruppo: str
    provincia_gruppo: str
    telefono_gruppo: str
    codice_fiscale_gruppo: str
    parrocchia_gruppo: str
    diocesi_gruppo: str
    denominazione_sociale_gruppo: str
    anomalie: list[AnomaliaRiga] = field(default_factory=list)


@dataclass(frozen=True)
class RisultatoParsing:
    """Esito del parsing del CSV. `anno_scout` è un metadato dell'intero
    file (colonna costante su tutte le righe), non varia riga per riga."""

    anno_scout: int | None
    righe: list[RigaBuonaCaccia] = field(default_factory=list)
    anomalie: list[AnomaliaRiga] = field(default_factory=list)
    anomalie_file: list[str] = field(default_factory=list)


def _spoglia(valore: str | None) -> str:
    if valore is None:
        return ""
    m = _RE_WRAP.match(valore)
    return m.group(1) if m else valore


def _parse_data(valore: str) -> date | None:
    if not valore:
        return None
    try:
        return datetime.strptime(valore, "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_intero(valore: str) -> int | None:
    if not valore:
        return None
    try:
        return int(valore)
    except ValueError:
        return None


def _apri_testo(source: Path | str | BinaryIO | TextIO) -> TextIO:
    if isinstance(source, (str, Path)):
        return open(source, encoding="utf-8-sig", newline="")
    dato = source.read()
    testo = dato.decode("utf-8-sig") if isinstance(dato, bytes) else dato
    return io.StringIO(testo)


def parse_csv(source: Path | str | BinaryIO | TextIO) -> RisultatoParsing:
    """
    Analizza il CSV "Ricerca Soci" di Buona Caccia: funzione pura, nessun
    accesso al database.

    Args:
        source: percorso del file oppure oggetto file-like (es.
                `request.FILES["csv"]`).

    Returns:
        RisultatoParsing con l'anno scout dichiarato dal file e una riga per
        socio, ciascuna con le proprie anomalie non bloccanti.
    """
    flusso = _apri_testo(source)
    try:
        prima_riga = flusso.readline()
        if not prima_riga.startswith("sep="):
            return RisultatoParsing(
                anno_scout=None,
                anomalie_file=["Prima riga inattesa: il file non inizia con 'sep=,' (§6.1)."],
            )
        return _analizza(csv.DictReader(flusso))
    finally:
        flusso.close()


def _analizza(reader: csv.DictReader) -> RisultatoParsing:
    righe: list[RigaBuonaCaccia] = []
    anomalie: list[AnomaliaRiga] = []
    anomalie_file: list[str] = []
    anno_scout: int | None = None

    for numero, grezza in enumerate(reader, start=2):  # la riga 1 è "sep=,"
        valori = {chiave: _spoglia(v) for chiave, v in grezza.items() if chiave}

        anno_riga = _parse_intero(valori.get("ANNO SCOUT", ""))
        if anno_riga is not None:
            if anno_scout is None:
                anno_scout = anno_riga
            elif anno_riga != anno_scout:
                anomalie_file.append(
                    f"Riga {numero}: ANNO SCOUT={anno_riga}, diverso dal valore già "
                    f"letto ({anno_scout}). File ambiguo, parsing interrotto."
                )
                return RisultatoParsing(anno_scout=None, anomalie_file=anomalie_file)

        riga, anomalie_riga = _analizza_riga(numero, valori)
        anomalie.extend(anomalie_riga)
        if riga is not None:
            righe.append(riga)

    righe, anomalie = _rileva_ordinali_ambigui(righe, anomalie)

    if anno_scout is None:
        anomalie_file.append("Nessuna riga valida: impossibile determinare ANNO SCOUT.")

    return RisultatoParsing(
        anno_scout=anno_scout, righe=righe, anomalie=anomalie, anomalie_file=anomalie_file
    )


def _analizza_riga(
    numero: int, v: dict[str, str]
) -> tuple[RigaBuonaCaccia | None, list[AnomaliaRiga]]:
    codice_socio = v.get("CODICE SOCIO", "").strip()
    ordinale = v.get("ORDINALE", "").strip()

    if not codice_socio:
        return None, [
            AnomaliaRiga(numero, ERRORE, "CODICE SOCIO", "Campo mancante: riga scartata.")
        ]
    if not ordinale or not _RE_ORDINALE.match(ordinale):
        return None, [
            AnomaliaRiga(
                numero,
                ERRORE,
                "ORDINALE",
                f"Valore '{ordinale}' non conforme a 'E' + 4 cifre: riga scartata.",
                codice_socio,
            )
        ]

    anomalie: list[AnomaliaRiga] = []

    data_nascita_grezza = v.get("DATA NASCITA", "").strip()
    data_nascita = _parse_data(data_nascita_grezza)
    if data_nascita_grezza and data_nascita is None:
        anomalie.append(
            AnomaliaRiga(
                numero,
                AVVISO,
                "DATA NASCITA",
                f"Valore '{data_nascita_grezza}' non parsabile (atteso gg/mm/aaaa).",
                codice_socio,
            )
        )

    sesso = v.get("SESSO", "").strip()
    if sesso and sesso not in {"M", "F"}:
        anomalie.append(
            AnomaliaRiga(numero, AVVISO, "SESSO", f"Valore '{sesso}' fuori da M/F.", codice_socio)
        )

    livello_foca_grezzo = v.get("LIVELLO FOCA", "").strip()
    livello_foca = _parse_intero(livello_foca_grezzo)
    if livello_foca_grezzo and livello_foca is None:
        anomalie.append(
            AnomaliaRiga(
                numero,
                AVVISO,
                "LIVELLO FOCA",
                f"Valore '{livello_foca_grezzo}' non intero.",
                codice_socio,
            )
        )

    status_socio = v.get("STATUS SOCIO", "").strip()
    if status_socio and status_socio not in _STATUS_SOCIO_NOTI:
        anomalie.append(
            AnomaliaRiga(
                numero,
                AVVISO,
                "STATUS SOCIO",
                f"Valore '{status_socio}' non fra quelli noti ({', '.join(sorted(_STATUS_SOCIO_NOTI))}).",
                codice_socio,
            )
        )

    riga = RigaBuonaCaccia(
        numero_riga=numero,
        codice_socio=codice_socio,
        nome=v.get("NOME", "").strip(),
        cognome=v.get("COGNOME", "").strip(),
        sesso=sesso,
        data_nascita=data_nascita,
        comune_nascita=v.get("COMUNE NASCITA", "").strip(),
        codice_fiscale=v.get("CODICE FISCALE", "").strip(),
        nazionalita=v.get("NAZIONALITA", "").strip(),
        indirizzo=v.get("INDIRIZZO", "").strip(),
        civico=v.get("CIVICO", "").strip(),
        comune_residenza=v.get("COMUNE RESIDENZA", "").strip(),
        provincia_residenza=v.get("PROVINCIA RESIDENZA", "").strip(),
        cap=v.get("CAP", "").strip(),
        email=v.get("EMAIL", "").strip(),
        cellulare=v.get("CELLULARE", "").strip(),
        professione=v.get("PROFESSIONE", "").strip(),
        livello_foca=livello_foca,
        ingresso_coca=v.get("INGRESSO COCA", "").strip(),
        comunita_socio=v.get("COMUNITA SOCIO", "").strip(),
        status_socio=status_socio,
        ordinale=ordinale,
        gruppo_nome=v.get("GRUPPO", "").strip(),
        email_gruppo=v.get("EMAIL GRUPPO", "").strip(),
        indirizzo_gruppo=v.get("INDIRIZZO GRUPPO", "").strip(),
        civico_gruppo=v.get("CIVICO GRUPPO", "").strip(),
        cap_gruppo=v.get("CAP GRUPPO", "").strip(),
        comune_gruppo=v.get("RESIDENZA GRUPPO", "").strip(),
        provincia_gruppo=v.get("PROVINCIA GRUPPO", "").strip(),
        telefono_gruppo=v.get("TELEFONO GRUPPO", "").strip(),
        codice_fiscale_gruppo=v.get("CODICE FISCALE GRUPPO", "").strip(),
        parrocchia_gruppo=v.get("PARROCCHIA GRUPPO", "").strip(),
        diocesi_gruppo=v.get("DIOCESI GRUPPO", "").strip(),
        denominazione_sociale_gruppo=v.get("DENOM. SOCIALE GRUPPO", "").strip(),
        anomalie=anomalie,
    )
    return riga, anomalie


def _rileva_ordinali_ambigui(
    righe: list[RigaBuonaCaccia], anomalie: list[AnomaliaRiga]
) -> tuple[list[RigaBuonaCaccia], list[AnomaliaRiga]]:
    """Due righe con lo stesso codice_socio ma ORDINALE diversi nello stesso
    file sono un dato ambiguo: mai un "vince l'ultima riga" indovinato,
    entrambe le righe vanno scartate e segnalate."""
    ordinali_per_socio: dict[str, set[str]] = {}
    for r in righe:
        ordinali_per_socio.setdefault(r.codice_socio, set()).add(r.ordinale)

    ambigui = {codice for codice, ordinali in ordinali_per_socio.items() if len(ordinali) > 1}
    if not ambigui:
        return righe, anomalie

    for r in righe:
        if r.codice_socio in ambigui:
            anomalie.append(
                AnomaliaRiga(
                    r.numero_riga,
                    ERRORE,
                    "ORDINALE",
                    f"Il socio {r.codice_socio} compare con ordinali diversi nello "
                    "stesso file: righe scartate, dato ambiguo.",
                    r.codice_socio,
                )
            )
    righe_pulite = [r for r in righe if r.codice_socio not in ambigui]
    return righe_pulite, anomalie
