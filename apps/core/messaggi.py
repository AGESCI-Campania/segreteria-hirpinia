"""Pulizia dei messaggi d'errore del service layer prima che arrivino
all'utente: i codici di decisione (D-NN, A-NN) servono a chi legge il
codice, mai all'interfaccia."""

import re

_CODICE_DECISIONE = re.compile(r"\s*\([A-Z]+-\d+(?:/[A-Z]+-\d+)*\)\.?\s*$")


def _pulisci(testo: str) -> str:
    return _CODICE_DECISIONE.sub("", testo).rstrip()


def messaggio_utente(exc: Exception) -> str:
    """Testo da mostrare all'utente per una PermissionDenied/ValidationError
    del service layer, senza i codici di decisione interni."""
    grezzo = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return _pulisci(grezzo)


def messaggi_per_campo(exc: Exception) -> dict[str, str] | None:
    """Se `exc` porta un dizionario di errori per-campo (es.
    `Partecipazione.clean()`), restituisce `{campo: messaggio_pulito}`.
    `None` se l'eccezione non ha una struttura per-campo (va trattata come
    errore generico con `messaggio_utente()`)."""
    message_dict = getattr(exc, "message_dict", None)
    if message_dict is None:
        return None
    return {campo: _pulisci("; ".join(msgs)) for campo, msgs in message_dict.items()}
