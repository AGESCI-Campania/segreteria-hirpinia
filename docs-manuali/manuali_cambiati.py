"""Manuali da rigenerare e allegare a una release: quelli cambiati dalla
release precedente (workflow release-manuale.yml). Stampa una configurazione
MkDocs per riga, nessuna se non è cambiato nulla.

Un manuale è cambiato se cambiano i suoi testi (la cartella), la sua
configurazione MkDocs, lo stile comune dei PDF o le pagine che descrive
(pagine.toml). La guida dei capigruppo segue `docs-utente/` e `mkdocs.yml`.
Senza una release precedente valgono tutti.

    python docs-manuali/manuali_cambiati.py <tag precedente> <tag della release>
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
import tomllib
from pathlib import Path

CARTELLA = Path(__file__).parent

# Comuni a tutti i PDF: stile (docs-manuali/pdf/) e logo della copertina.
COMUNI = ("docs-manuali/pdf/*", "static/pdf/img/logo_zona.png")

GUIDA = {"configurazione": "mkdocs.yml", "cartella": "docs-utente", "pagine": []}


def file_cambiati(precedente: str, release: str) -> list[str] | None:
    uscita = subprocess.run(
        ["git", "diff", "--name-only", f"{precedente}..{release}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if uscita.returncode != 0:
        return None
    return [riga for riga in uscita.stdout.splitlines() if riga]


def manuali(configurazione: dict) -> dict[str, dict]:
    """Ogni manuale con la sua configurazione MkDocs (mkdocs-<nome>.yml)."""
    risultato = {"guida": GUIDA}
    for nome, dati in configurazione.items():
        risultato[nome] = {**dati, "configurazione": f"mkdocs-{nome}.yml"}
    return risultato


def cambiati(file: list[str] | None, elenco: dict[str, dict]) -> list[str]:
    configurazioni = []
    for dati in elenco.values():
        cartella = dati["cartella"].rstrip("/") + "/"
        modelli = [*dati["pagine"], *COMUNI, dati["configurazione"]]
        if (
            file is None
            or any(f.startswith(cartella) for f in file)
            or any(fnmatch.fnmatch(f, m) for f in file for m in modelli)
        ):
            configurazioni.append(dati["configurazione"])
    return configurazioni


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    precedente, release = sys.argv[1], sys.argv[2]
    configurazione = tomllib.loads((CARTELLA / "pagine.toml").read_text())
    file = file_cambiati(precedente, release) if precedente else None
    for voce in cambiati(file, manuali(configurazione)):
        print(voce)
    return 0


if __name__ == "__main__":
    sys.exit(main())
