"""Unit tests for parser helper functions."""

import pytest
from datetime import datetime

from apps.anagrafica.parser.autorizzazioni import (
    _branca,
    _genere_unita,
    _is_formation_page,
    _parse_date,
    _extract_pdf_metadata,
    _parse_person_block,
)


# ── _branca ───────────────────────────────────────────────────────────────────

class TestBranca:
    def test_branco(self):
        assert _branca("BRANCO/CERCHIO MISTO") == "L/C"

    def test_cerchio(self):
        assert _branca("CERCHIO FEMMINILE") == "L/C"

    def test_reparto(self):
        assert _branca("REPARTO MASCHILE") == "E/G"

    def test_clan(self):
        assert _branca("CLAN/FUOCO") == "R/S"

    def test_fuoco(self):
        assert _branca("FUOCO") == "R/S"

    def test_comunita_capi(self):
        assert _branca("COMUNITA` CAPI") == "Adulti"

    def test_unknown(self):
        assert _branca("UNITÀ SCONOSCIUTA") == "SCONOSCIUTA"

    def test_case_insensitive(self):
        assert _branca("branco misto") == "L/C"


# ── _genere_unita ─────────────────────────────────────────────────────────────

class TestGenereUnita:
    def test_maschile(self):
        assert _genere_unita("BRANCO/CERCHIO MASCHILE") == "MASCHILE"

    def test_femminile(self):
        assert _genere_unita("CERCHIO FEMMINILE") == "FEMMINILE"

    def test_misto_explicit(self):
        assert _genere_unita("REPARTO MISTO") == "MISTO"

    def test_misto_default(self):
        assert _genere_unita("REPARTO") == "MISTO"

    def test_comunita_capi_default_misto(self):
        assert _genere_unita("COMUNITA` CAPI") == "MISTO"


# ── _is_formation_page ────────────────────────────────────────────────────────

class TestIsFormationPage:
    def test_detects_formation(self):
        text = "G1 COMUNITA` CAPI - Formazione e impegni formativi\nsome content"
        assert _is_formation_page(text) is True

    def test_normal_page(self):
        text = "G1 COMUNITA` CAPI\n1234567 ROSSI MARIO Funzione/Incarico: CAPO UNITÀ"
        assert _is_formation_page(text) is False


# ── _parse_date ───────────────────────────────────────────────────────────────

class TestParseDate:
    def test_valid(self):
        assert _parse_date("31/10/2025") == datetime(2025, 10, 31)

    def test_invalid(self):
        assert _parse_date("not-a-date") == datetime.min

    def test_empty(self):
        assert _parse_date("") == datetime.min


# ── _extract_pdf_metadata ─────────────────────────────────────────────────────

class TestExtractPdfMetadata:
    _PAGE = (
        "AGESCI | BuonaStrada Tipo di documento | Richiesta Autorizzazione\n"
        "Modello Autorizzazione Unità - Anno 2026 Gruppo: ALTAVILLA - E3279\n"
        "(dati aggiornati al 31/10/2025)\n"
    )

    def test_anno(self):
        anno, *_ = _extract_pdf_metadata([self._PAGE])
        assert anno == 2026

    def test_gruppo_nome(self):
        _, nome, *_ = _extract_pdf_metadata([self._PAGE])
        assert nome == "ALTAVILLA"

    def test_gruppo_codice(self):
        _, _, codice, _ = _extract_pdf_metadata([self._PAGE])
        assert codice == "E3279"

    def test_data_aggiornamento(self):
        *_, data = _extract_pdf_metadata([self._PAGE])
        assert data == datetime(2025, 10, 31)

    def test_missing_header(self):
        anno, nome, codice, data = _extract_pdf_metadata(["nessun contenuto valido"])
        assert anno == 0
        assert nome == ""
        assert codice == ""
        assert data == datetime.min


# ── _parse_person_block ───────────────────────────────────────────────────────

class TestParsePersonBlock:

    def test_standard_two_lines(self):
        """Function fits on one line, FOCA on second."""
        lines = [
            "1234567 ROSSI ROBERTA Funzione/Incarico: CAPO GRUPPO Anno di ingresso in COCA: 2019",
            "F Nata a: ROMA il 15/03/1985 Livello FOCA: 3 Ultima formaz. CG:",
        ]
        p = _parse_person_block(lines)
        assert p["codice_socio"] == "1234567"
        assert p["nome"] == "ROSSI ROBERTA"
        assert p["funzione"] == "CAPO GRUPPO"
        assert p["genere"] == "F"
        assert p["foca"] == 3

    def test_wrapped_function_three_lines(self):
        """Function wraps to second line, FOCA on third line."""
        lines = [
            "9876543 BIANCHI MARIO Funzione/Incarico: ASSISTENTE ECCLESIASTICO DI Anno di ingresso in COCA: 2015",
            "M Nato a: TORINO il 12/06/1975 GRUPPO",
            "Livello FOCA: 2",
        ]
        p = _parse_person_block(lines)
        assert p["codice_socio"] == "9876543"
        assert p["funzione"] == "ASSISTENTE ECCLESIASTICO DI GRUPPO"
        assert p["genere"] == "M"
        assert p["foca"] == 2

    def test_ultima_formaz_wraps_but_function_complete(self):
        """Ultima formaz. CG wraps to a third line; function is already complete."""
        lines = [
            "5551234 VERDI GIOVANNI Funzione/Incarico: CAPO GRUPPO Anno di ingresso in COCA: 2014",
            "M Nato a: FIRENZE il 20/08/1988 Livello FOCA: 5 Ultima formaz. CG: 03/03/2024 CAMPO",
            "PER CAPI GRUPPO",
        ]
        p = _parse_person_block(lines)
        assert p["funzione"] == "CAPO GRUPPO"
        assert p["foca"] == 5

    def test_short_codice(self):
        """4-digit codice socio."""
        lines = [
            "9999 BIANCHI LUCA Funzione/Incarico: CAPO UNITÀ Anno di ingresso in COCA: 2020",
            "M Nato a: ROMA il 01/01/2000 Livello FOCA: 4",
        ]
        p = _parse_person_block(lines)
        assert p["codice_socio"] == "9999"

    def test_empty_lines_returns_none(self):
        assert _parse_person_block([]) is None

    def test_invalid_first_line_returns_none(self):
        assert _parse_person_block(["non è un record valido"]) is None

    def test_foca_level_extracted(self):
        lines = [
            "7774321 ESPOSITO ANDREA Funzione/Incarico: AIUTO CAPO UNITÀ Anno di ingresso in COCA: 2025",
            "M Nato a: NAPOLI il 03/11/2000 Livello FOCA: 2",
        ]
        p = _parse_person_block(lines)
        assert p["foca"] == 2

    def test_funzione_missing_returns_sconosciuta(self):
        """If no Funzione/Incarico pattern found, default to SCONOSCIUTA."""
        lines = [
            "1234567 VERDI GIUSEPPE Funzione/Incarico:  Anno di ingresso in COCA: 2020",
            "M Nato a: NAPOLI il 01/06/1990 Livello FOCA: 3",
        ]
        p = _parse_person_block(lines)
        assert p is not None
        assert p["funzione"] == "SCONOSCIUTA"
