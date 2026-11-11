"""Risorse condivise dei PDF WeasyPrint con la carta intestata della Zona
(templates/pdf/carta_intestata*.html): nota spese, foglio presenze, verbali
delle assemblee, riepilogo dei contributi.

La carta intestata riproduce quella ufficiale della Zona (modello Word in
docs/ignored/carta_intestata.docx, non versionato): banda e loghi sono le
immagini di quel modello, in static/pdf/img/."""

from __future__ import annotations

from django.contrib.staticfiles import finders

# Dati della Zona stampati nella carta intestata e citati nei verbali.
ZONA = {
    "nome": "Zona Hirpinia",
    "regione": "Campania",
    "indirizzo": "Via Episcopio SNC, 83100 Avellino",
    "codice_fiscale": "92048600644",
    "email": "zonahirpinia@campania.agesci.it",
    "pec": "zonahirpinia@pec.agesci.it",
    "runts": "Iscritta al Registro Unico Nazionale del Terzo Settore – repertorio n. 66955 "
    "del 07/11/2022",
}


def contesto_carta_intestata() -> dict:
    """Dati della Zona e percorsi su disco dei loghi (letti da WeasyPrint con
    `file://`) per i template della carta intestata."""
    return {
        "zona": ZONA,
        "banda_path": finders.find("pdf/img/carta_intestata_banda.jpg"),
        "logo_zona_path": finders.find("pdf/img/logo_zona.png"),
        "loghi_piede_path": finders.find("pdf/img/loghi_wosm_wagggs.jpg"),
    }
