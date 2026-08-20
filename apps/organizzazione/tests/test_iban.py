"""Validazione IBAN (D-14): struttura, lunghezza per paese, checksum mod-97."""

import pytest
from django.core.exceptions import ValidationError

from apps.organizzazione.iban import valida_iban

IBAN_IT_VALIDO = "IT60X0542811101000000123456"


class TestValidaIban:
    def test_iban_valido_non_solleva(self):
        valida_iban(IBAN_IT_VALIDO)  # non deve sollevare

    def test_iban_vuoto_rifiutato(self):
        with pytest.raises(ValidationError):
            valida_iban("")

    def test_checksum_errato_rifiutato(self):
        errato = "IT61X0542811101000000123456"  # cifre di controllo alterate
        with pytest.raises(ValidationError):
            valida_iban(errato)

    def test_lunghezza_errata_per_paese_rifiutata(self):
        troppo_corto = IBAN_IT_VALIDO[:-1]
        with pytest.raises(ValidationError):
            valida_iban(troppo_corto)

    def test_paese_non_riconosciuto_rifiutato(self):
        with pytest.raises(ValidationError):
            valida_iban("ZZ60X0542811101000000123456")

    def test_caratteri_non_ammessi_rifiutati(self):
        with pytest.raises(ValidationError):
            valida_iban("IT60 X054 2811 1010 0000 0123 456")
