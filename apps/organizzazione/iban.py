"""Validazione IBAN (D-14): lunghezza per paese e checksum mod-97 (ISO 13616),
non solo regex di forma. Riusata sia dal gate di chiusura campagna
(`apps/contributi/campagne.py::chiudi_campagna`) sia dal validatore di campo
su `Gruppo.iban`."""

from __future__ import annotations

from django.core.exceptions import ValidationError

# Lunghezza esatta dell'IBAN per paese (registro pubblico IBAN, ISO
# 13616/SWIFT). Un codice paese assente dalla tabella non viene validato per
# lunghezza indovinando un valore: è un errore esplicito (anti-confabulazione,
# CLAUDE.md).
LUNGHEZZA_PER_PAESE: dict[str, int] = {
    "AD": 24,
    "AE": 23,
    "AL": 28,
    "AT": 20,
    "AZ": 28,
    "BA": 20,
    "BE": 16,
    "BG": 22,
    "BH": 22,
    "BR": 29,
    "BY": 28,
    "CH": 21,
    "CR": 22,
    "CY": 28,
    "CZ": 24,
    "DE": 22,
    "DK": 18,
    "DO": 28,
    "EE": 20,
    "EG": 29,
    "ES": 24,
    "FI": 18,
    "FO": 18,
    "FR": 27,
    "GB": 22,
    "GE": 22,
    "GI": 23,
    "GL": 18,
    "GR": 27,
    "GT": 28,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IL": 23,
    "IQ": 23,
    "IS": 26,
    "IT": 27,
    "JO": 30,
    "KW": 30,
    "KZ": 20,
    "LB": 28,
    "LC": 32,
    "LI": 21,
    "LT": 20,
    "LU": 20,
    "LV": 21,
    "LY": 25,
    "MC": 27,
    "MD": 24,
    "ME": 22,
    "MK": 19,
    "MR": 27,
    "MT": 31,
    "MU": 30,
    "NL": 18,
    "NO": 15,
    "PK": 24,
    "PL": 28,
    "PS": 29,
    "PT": 25,
    "QA": 29,
    "RO": 24,
    "RS": 22,
    "SA": 24,
    "SC": 31,
    "SE": 24,
    "SI": 19,
    "SK": 24,
    "SM": 27,
    "ST": 25,
    "SV": 28,
    "TL": 23,
    "TN": 24,
    "TR": 26,
    "UA": 29,
    "VA": 22,
    "VG": 24,
    "XK": 20,
}


def _mod_97(iban_normalizzato: str) -> int:
    riordinato = iban_normalizzato[4:] + iban_normalizzato[:4]
    numerico = "".join(str(ord(c) - 55) if c.isalpha() else c for c in riordinato)
    return int(numerico) % 97


def valida_iban(iban: str) -> None:
    """Solleva `ValidationError` se `iban` non è un IBAN valido. Non
    normalizza né corregge: uno spazio o un trattino nel valore salvato è già
    un dato da segnalare, non da indovinare."""
    if not iban:
        raise ValidationError("IBAN mancante.")
    if not (iban[:2].isalpha() and iban[:2].isupper() and iban[2:4].isdigit()):
        raise ValidationError(f"{iban}: formato non valido (attesi 2 lettere + 2 cifre iniziali).")
    if not iban.isalnum():
        raise ValidationError(f"{iban}: contiene caratteri non ammessi (spazi o simboli).")

    paese = iban[:2]
    lunghezza_attesa = LUNGHEZZA_PER_PAESE.get(paese)
    if lunghezza_attesa is None:
        raise ValidationError(f"{iban}: codice paese '{paese}' non riconosciuto.")
    if len(iban) != lunghezza_attesa:
        raise ValidationError(
            f"{iban}: lunghezza {len(iban)} non valida per il paese '{paese}' "
            f"(attesa {lunghezza_attesa})."
        )
    if _mod_97(iban) != 1:
        raise ValidationError(f"{iban}: checksum non valido (ISO 13616).")
