"""Lettura dei messaggi di Mailpit attraverso la sua API web, sulla rete
interna (`EMAIL_MAILPIT_API_URL`). Serve solo alla pagina delle email di
un'assemblea di prova «solo Mailpit» (docs/plan_preparazione_assemblea.md,
D28): l'interfaccia di Mailpit resta non esposta.

Nessun log del contenuto dei messaggi (dati personali, codici): in caso di
errore solo che Mailpit non ha risposto."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDI = 5
LIMITE_MESSAGGI = 200


class MailpitNonRaggiungibile(Exception):
    pass


@dataclass(frozen=True)
class Messaggio:
    id: str
    destinatari: list[str]
    oggetto: str
    data: datetime | None
    etichette: list[str]
    testo: str


def configurato() -> bool:
    """Si possono sia mandare sia leggere le email su Mailpit."""
    return bool(settings.EMAIL_MAILPIT_HOST and settings.EMAIL_MAILPIT_API_URL)


def _get(percorso: str, parametri: dict | None = None) -> dict:
    base = settings.EMAIL_MAILPIT_API_URL.rstrip("/")
    url = f"{base}{percorso}"
    if parametri:
        url += "?" + urllib.parse.urlencode(parametri)
    try:
        # Indirizzo dalla configurazione del server, mai dall'utente.
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDI) as risposta:  # noqa: S310
            return json.load(risposta)
    except Exception as errore:
        logger.warning("Mailpit non raggiungibile: %s", type(errore).__name__)
        raise MailpitNonRaggiungibile from None


def _data(valore: str) -> datetime | None:
    try:
        return datetime.fromisoformat(valore.replace("Z", "+00:00"))
    except AttributeError, ValueError:
        return None


def messaggi_con_etichetta(etichetta: str) -> list[Messaggio]:
    """Messaggi con l'etichetta (tag di Mailpit), dal più recente, con il
    testo semplice."""
    if not settings.EMAIL_MAILPIT_API_URL:
        raise MailpitNonRaggiungibile
    elenco = _get("/api/v1/search", {"query": f'tag:"{etichetta}"', "limit": LIMITE_MESSAGGI})
    risultato = []
    for voce in elenco.get("messages") or []:
        dettaglio = _get(f"/api/v1/message/{urllib.parse.quote(voce['ID'])}")
        risultato.append(
            Messaggio(
                id=voce["ID"],
                destinatari=[d.get("Address", "") for d in voce.get("To") or []],
                oggetto=voce.get("Subject", ""),
                data=_data(voce.get("Created", "")),
                etichette=list(voce.get("Tags") or []),
                testo=dettaglio.get("Text", ""),
            )
        )
    return risultato
