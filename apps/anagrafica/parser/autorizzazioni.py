"""Parser dei PDF di autorizzazione dei gruppi AGESCI.

Codice derivato dal progetto `autorizzazioni-agesci` v1.0.1 (Andrea Bruno, MIT),
internalizzato in Catello per evitare una dipendenza esterna.

Le regex e le regole di riconoscimento sono state validate su un campione reale di
15 PDF / 12 gruppi / 218 record (anno 2026). Non modificarle senza rieseguire i test
di integrazione: sono il risultato di tentativi successivi su un text layer che
mescola le porzioni di testo.

API pubblica:
    parse_pdf(source)              -> ParseResult   (un singolo file, anche in memoria)
    parse_year(input_dir, year)    -> list[dict]    (batch da cartella per anno)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import pdfplumber


# ── Regex patterns ────────────────────────────────────────────────────────────

_RE_HEADER = re.compile(
    r"Modello Autorizzazione Unit.+?Anno\s+(\d{4})\s+Gruppo:\s+(.+?)\s*-\s*(\w+)"
)
_RE_AGGIORNAMENTO = re.compile(r"\(dati aggiornati al\s+(\d{2}/\d{2}/\d{4})\)")
_RE_UNIT_HEADER = re.compile(r"^([A-Z]\d+)\s+(.+?)(?:\s+-\s+Formazione e impegni formativi)?$")
_RE_PERSON_START = re.compile(r"^(\d{4,8})\s+([A-ZÀÈÉÌÒÙÁÉÍÓÚ][A-ZÀÈÉÌÒÙÁÉÍÓÚ\s']+?)\s+Funzione/Incarico:")
_RE_FUNZIONE = re.compile(r"Funzione/Incarico:\s+(.+?)\s+Anno di ingresso in COCA:")
_RE_FOCA = re.compile(r"Livello FOCA:\s*(\d+)")
_RE_GENDER = re.compile(r"^([MF])\s+(?:Nato|Nata) a:")
_RE_BIRTH_DATE = re.compile(r"il\s+\d{2}/\d{2}/\d{4}\s+(.*)")

_IGNORE_LINE = re.compile(
    r"^(AGESCI|Modello Autorizzazione|Data creazione:|Progetto formativo|"
    r"\* il |Impegni per la Zona|IL CAPO )"
)


# ── Branch / unit-gender detection ───────────────────────────────────────────

def _branca(unit_name: str) -> str:
    u = unit_name.upper()
    if "COMUNITA" in u:
        return "Adulti"
    if "BRANCO" in u or "CERCHIO" in u:
        return "L/C"
    if "REPARTO" in u:
        return "E/G"
    if "CLAN" in u or "FUOCO" in u:
        return "R/S"
    return "SCONOSCIUTA"


def _genere_unita(unit_name: str) -> str:
    u = unit_name.upper()
    if "MASCHILE" in u:
        return "MASCHILE"
    if "FEMMINILE" in u:
        return "FEMMINILE"
    return "MISTO"


# ── PDF-level extraction ──────────────────────────────────────────────────────

def _parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%d/%m/%Y")
    except ValueError:
        return datetime.min


def _extract_pdf_metadata(pages_text: list[str]) -> tuple[int, str, str, str, datetime]:
    """Return (anno, gruppo_nome, gruppo_codice, raw_header, data_aggiornamento)."""
    full = "\n".join(pages_text)
    anno = 0
    gruppo_nome = ""
    gruppo_codice = ""
    data_agg = datetime.min

    m = _RE_HEADER.search(full)
    if m:
        anno = int(m.group(1))
        gruppo_nome = m.group(2).strip()
        gruppo_codice = m.group(3).strip()

    m = _RE_AGGIORNAMENTO.search(full)
    if m:
        data_agg = _parse_date(m.group(1))

    return anno, gruppo_nome, gruppo_codice, data_agg


def _is_formation_page(text: str) -> bool:
    return "Formazione e impegni formativi" in text


def _parse_person_block(lines: list[str]) -> dict | None:
    """Parse a 2-3 line person record and return a dict, or None on failure."""
    if not lines:
        return None

    line0 = lines[0]
    codice_m = re.match(r"^(\d{4,8})\s+", line0)
    if not codice_m:
        return None
    codice = codice_m.group(1)

    nome_m = re.match(r"^\d{4,8}\s+(.+?)\s+Funzione/Incarico:", line0)
    nome = nome_m.group(1).strip() if nome_m else ""

    func_m = _RE_FUNZIONE.search(line0)
    func_part1 = func_m.group(1).strip() if func_m else ""

    genere = ""
    foca = 0
    func_part2 = ""

    if len(lines) > 1:
        birth_line = lines[1]
        g_m = _RE_GENDER.match(birth_line)
        if g_m:
            genere = g_m.group(1)

        foca_m = _RE_FOCA.search(birth_line)
        if foca_m:
            foca = int(foca_m.group(1))
        else:
            # No FOCA on this line → text after birth date is function continuation
            after_m = _RE_BIRTH_DATE.search(birth_line)
            if after_m:
                remainder = after_m.group(1).strip()
                if remainder and not remainder.startswith("Livello"):
                    func_part2 = remainder

    if func_part2 and len(lines) > 2:
        foca_m = _RE_FOCA.search(lines[2])
        if foca_m:
            foca = int(foca_m.group(1))

    funzione = (func_part1 + (" " + func_part2 if func_part2 else "")).strip()
    if not funzione:
        funzione = "SCONOSCIUTA"

    return {
        "codice_socio": codice,
        "nome": nome,
        "funzione": funzione,
        "genere": genere,
        "foca": foca,
    }


@dataclass(frozen=True)
class ParseResult:
    """Esito del parsing di un singolo PDF di autorizzazione."""

    data_aggiornamento: datetime
    anno: int
    gruppo_nome: str
    gruppo_codice: str
    records: list[dict] = field(default_factory=list)

    @property
    def is_valido(self) -> bool:
        """True se il PDF è stato riconosciuto come autorizzazione di un gruppo."""
        return bool(self.gruppo_codice) and self.anno > 0


def parse_pdf(source: Path | str | BinaryIO) -> ParseResult:
    """
    Analizza un singolo PDF di autorizzazione.

    Args:
        source: percorso del file oppure oggetto file-like aperto in binario
                (es. `request.FILES["autorizzazione"]`).

    Returns:
        ParseResult con data di aggiornamento, anno, dati del gruppo e i record
        (uno per coppia capo/unità).
    """
    data_agg, anno, nome, codice, records = _parse_pdf(source)
    return ParseResult(
        data_aggiornamento=data_agg,
        anno=anno,
        gruppo_nome=nome,
        gruppo_codice=codice,
        records=records,
    )


def _parse_pdf(source: Path | str | BinaryIO) -> tuple[datetime, int, str, str, list[dict]]:
    """
    Parse a single PDF.
    Returns (data_aggiornamento, anno, gruppo_nome, gruppo_codice, records).
    """
    pages_text: list[str] = []

    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if _is_formation_page(text):
                continue
            pages_text.append(text)

    if not pages_text:
        return datetime.min, 0, "", "", []

    anno, gruppo_nome, gruppo_codice, data_agg = _extract_pdf_metadata(pages_text)
    records: list[dict] = []

    current_unit_code = ""
    current_unit_name = ""
    current_person_lines: list[str] = []

    def flush_person():
        nonlocal current_person_lines
        if current_person_lines:
            p = _parse_person_block(current_person_lines)
            if p:
                records.append({
                    "codice_socio": p["codice_socio"],
                    "nome": p["nome"],
                    "gruppo": gruppo_nome,
                    "codice_gruppo": gruppo_codice,
                    "unita": f"{current_unit_code} {current_unit_name}".strip(),
                    "branca": _branca(current_unit_name),
                    "genere_unita": _genere_unita(current_unit_name),
                    "genere": p["genere"],
                    "livello_foca": p["foca"],
                    "funzione": p["funzione"],
                    "anno": anno,
                })
        current_person_lines = []

    for page_text in pages_text:
        for line in page_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if _IGNORE_LINE.match(line):
                continue

            # Detect unit header
            unit_m = _RE_UNIT_HEADER.match(line)
            if unit_m and not _RE_PERSON_START.match(line):
                unit_code_candidate = unit_m.group(1)
                unit_name_candidate = unit_m.group(2).strip()
                # Validate: real unit headers have known keywords or COMUNITA
                keywords = ("COMUNITA", "BRANCO", "CERCHIO", "REPARTO", "CLAN", "FUOCO")
                if any(k in unit_name_candidate.upper() for k in keywords):
                    flush_person()
                    current_unit_code = unit_code_candidate
                    current_unit_name = unit_name_candidate
                    continue

            # Detect start of a new person record
            if _RE_PERSON_START.match(line):
                flush_person()
                current_person_lines = [line]
                continue

            # Continuation of current person block (gender/birth or FOCA line)
            if current_person_lines:
                current_person_lines.append(line)

    flush_person()
    return data_agg, anno, gruppo_nome, gruppo_codice, records


# ── Public API ────────────────────────────────────────────────────────────────

def parse_year(input_dir: str | Path, year: int | None = None) -> list[dict]:
    """
    Parse all PDF authorization files for a given year.

    Automatically selects the most recent PDF when multiple files exist for
    the same group (identified by the group code in the PDF header).

    Args:
        input_dir: Root directory containing year sub-folders.
        year:      Year to process; defaults to the most recent year found.

    Returns:
        List of dicts with one entry per (capo, unit) combination.
    """
    input_dir = Path(input_dir)

    # Resolve year
    if year is None:
        year_dirs = sorted(
            (d for d in input_dir.iterdir() if d.is_dir() and d.name.isdigit()),
            key=lambda d: int(d.name),
        )
        if not year_dirs:
            raise FileNotFoundError(f"No year directories found in {input_dir}")
        year_dir = year_dirs[-1]
        year = int(year_dir.name)
    else:
        year_dir = input_dir / str(year)
        if not year_dir.is_dir():
            raise FileNotFoundError(f"Directory not found: {year_dir}")

    pdfs = list(year_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found in {year_dir}")

    # Parse every PDF, keeping only the most recent per group code
    best: dict[str, tuple[datetime, list[dict]]] = {}

    for pdf_path in pdfs:
        data_agg, _anno, _nome, gruppo_codice, records = _parse_pdf(pdf_path)
        if not gruppo_codice:
            continue
        prev_date, _ = best.get(gruppo_codice, (datetime.min, []))
        if data_agg > prev_date:
            best[gruppo_codice] = (data_agg, records)

    all_records: list[dict] = []
    for _date, records in best.values():
        all_records.extend(records)

    return all_records
