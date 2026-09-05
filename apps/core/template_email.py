"""Motore di sostituzione ridotto per `TemplateEmail` (M8.2, D-XX). Solo
`{{ variabile }}`: nessun tag Django (`{% %}`), nessun filtro, nessuna
chiamata a metodo — il contenuto arriva da un form via interfaccia, non più
da un file sotto controllo di versione, e non deve poter eseguire logica
arbitraria. I chiamanti passano un contesto già "piatto" (stringhe finali,
non oggetti modello): ogni `{% if %}`/filtro che il vecchio template Django
faceva va risolto in Python prima di chiamare `sostituisci_placeholder()`."""

from __future__ import annotations

import re

from .models import CodiceTemplateEmail

_RE_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# Variabile globale (M-usabilita-template-email): a differenza di quelle in
# VARIABILI_PER_CODICE, non è specifica di un template ma disponibile ovunque
# tranne che nell'oggetto — lì il prefisso è già applicato automaticamente da
# `applica_prefisso_oggetto`, per evitare la duplicazione segnalata in issue
# (vincolo imposto anche a monte in `TemplateEmailForm.clean_oggetto`).
VARIABILE_PREFISSO_OGGETTO = "subjectPrefix"
VARIABILI_GLOBALI: list[str] = [VARIABILE_PREFISSO_OGGETTO]

# Elenco delle variabili disponibili per ciascun codice, mostrato in UI come
# legenda (M8.2). Deve restare sincronizzato a mano con il contesto
# effettivamente costruito in ogni punto di invio (apps/accounts/inviti.py,
# apps/accounts/deleghe.py, apps/accounts/signals.py,
# apps/anagrafica/incarichi.py) — nessun meccanismo automatico lo verifica.
VARIABILI_PER_CODICE: dict[str, list[str]] = {
    CodiceTemplateEmail.INVITO_ATTIVAZIONE: [
        "codice",
        "email",
        "scadenza",
        "link_attivazione",
        "link_recupero",
        "paragrafo_gruppo",
    ],
    CodiceTemplateEmail.FINE_IMPERSONIFICAZIONE: ["amministratore", "quando"],
    CodiceTemplateEmail.DELEGA_CREATA: ["ruolo", "delegato", "scadenza"],
    CodiceTemplateEmail.DELEGA_REVOCATA: ["ruolo", "delegato", "revocata_da_frase"],
    CodiceTemplateEmail.INCARICO_ASSEGNATO: [
        "capo",
        "gruppo_servizio",
        "unita",
        "funzione",
        "assegnato_da",
    ],
    CodiceTemplateEmail.INCARICO_CESSATO: ["capo", "gruppo_servizio", "unita", "funzione"],
}


# Contesto di esempio per l'anteprima e l'invio di test (M8.4): valori
# plausibili, mai dati reali di soci/gruppi.
CONTESTO_ESEMPIO: dict[str, dict[str, str]] = {
    CodiceTemplateEmail.INVITO_ATTIVAZIONE: {
        "codice": "ABC123XY",
        "email": "mario.rossi@example.com",
        "scadenza": "31/12/2026 18:00",
        "link_attivazione": "https://catello.example.org/accounts/attiva/?email=...&codice=...",
        "link_recupero": "https://catello.example.org/accounts/recupero/",
        "paragrafo_gruppo": (
            "\nUna volta attivato l'account, potrai caricare le partecipazioni per il\n"
            "contributo del tuo gruppo da qui:\n"
            "https://catello.example.org/contributi/campagne/\n"
        ),
    },
    CodiceTemplateEmail.FINE_IMPERSONIFICAZIONE: {
        "amministratore": "Segreteria Zona",
        "quando": "31/12/2026 18:00",
    },
    CodiceTemplateEmail.DELEGA_CREATA: {
        "ruolo": "Capogruppo - E0133",
        "delegato": "Mario Rossi",
        "scadenza": "31/12/2026",
    },
    CodiceTemplateEmail.DELEGA_REVOCATA: {
        "ruolo": "Capogruppo - E0133",
        "delegato": "Mario Rossi",
        "revocata_da_frase": " da Segreteria Zona",
    },
    CodiceTemplateEmail.INCARICO_ASSEGNATO: {
        "capo": "Mario Rossi",
        "gruppo_servizio": "AVELLINO 1 (E0133)",
        "unita": "H1 BRANCO MISTO",
        "funzione": "Capo unità",
        "assegnato_da": "Segreteria Zona",
    },
    CodiceTemplateEmail.INCARICO_CESSATO: {
        "capo": "Mario Rossi",
        "gruppo_servizio": "AVELLINO 1 (E0133)",
        "unita": "H1 BRANCO MISTO",
        "funzione": "Capo unità",
    },
}


def sostituisci_placeholder(testo: str, contesto: dict[str, str]) -> str:
    """Un placeholder senza corrispondenza nel contesto (typo, campo
    dimenticato) diventa stringa vuota: non deve mai bloccare l'invio
    (decisione presa con l'utente)."""

    def _sostituisci(m: re.Match[str]) -> str:
        return str(contesto.get(m.group(1), ""))

    return _RE_PLACEHOLDER.sub(_sostituisci, testo)


def applica_prefisso_oggetto(oggetto: str, prefisso: str) -> str:
    prefisso = prefisso.strip()
    if not prefisso:
        return oggetto
    return f"{prefisso} - {oggetto}"


def contesto_con_variabili_globali(
    contesto: dict[str, str], prefisso_oggetto: str
) -> dict[str, str]:
    """Non muta il contesto passato dal chiamante: usato per il corpo e per
    la firma, mai per l'oggetto (vedi `applica_prefisso_oggetto`)."""
    esteso = dict(contesto)
    esteso.setdefault(VARIABILE_PREFISSO_OGGETTO, prefisso_oggetto)
    return esteso
