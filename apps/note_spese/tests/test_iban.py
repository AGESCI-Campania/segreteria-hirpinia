"""D-51: mascheratura IBAN (ultime quattro cifre visibili)."""

from apps.note_spese.iban import maschera_iban


def test_maschera_iban_standard() -> None:
    assert maschera_iban("IT60X0542811101000000123456") == "•" * 23 + "3456"


def test_maschera_iban_vuoto() -> None:
    assert maschera_iban("") == ""


def test_maschera_iban_corto() -> None:
    assert maschera_iban("AB12") == "••••"
