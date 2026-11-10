"""Risorse condivise dei PDF WeasyPrint con la carta intestata della Zona
(templates/pdf/carta_intestata*.html): nota spese, foglio presenze e verbali
delle assemblee."""

from __future__ import annotations

from django.contrib.staticfiles import finders


def percorsi_carta_intestata() -> dict[str, str | None]:
    """Percorsi su disco dei loghi, letti da WeasyPrint con `file://`."""
    return {
        "logo_zona_path": finders.find("note_spese/img/logo_zona.png"),
        "loghi_piede_path": finders.find("note_spese/img/loghi_wosm_waggs.png"),
    }
