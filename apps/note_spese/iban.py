"""Mascheratura dell'IBAN in `NotaSpese` (D-51): ultime quattro cifre visibili
a chiunque, il resto sostituito. La validazione del checksum riusa
`apps.organizzazione.iban.valida_iban` (D-69, nessuna logica duplicata) — non
reimplementata qui."""

from __future__ import annotations

CIFRE_VISIBILI = 4


def maschera_iban(iban: str) -> str:
    if not iban:
        return ""
    if len(iban) <= CIFRE_VISIBILI:
        return "•" * len(iban)
    return "•" * (len(iban) - CIFRE_VISIBILI) + iban[-CIFRE_VISIBILI:]
