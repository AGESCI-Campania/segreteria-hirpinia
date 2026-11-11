"""Avvisa se cambiano le pagine descritte da un manuale senza che cambi il
manuale (docs/plan_preparazione_assemblea.md, D34). Non blocca mai: stampa
un avviso nel formato delle GitHub Actions ed esce con 0.

    python docs-manuali/verifica_aggiornamento.py <commit di partenza>
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
import tomllib
from pathlib import Path

CARTELLA = Path(__file__).parent


def file_cambiati(partenza: str) -> list[str]:
    uscita = subprocess.run(
        ["git", "diff", "--name-only", f"{partenza}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if uscita.returncode != 0:
        print(f"::notice::Confronto con {partenza} non possibile: controllo dei manuali saltato.")
        return []
    return [riga for riga in uscita.stdout.splitlines() if riga]


def manuali_da_aggiornare(cambiati: list[str], configurazione: dict) -> dict[str, list[str]]:
    risultato = {}
    for manuale, dati in configurazione.items():
        toccate = [f for f in cambiati if any(fnmatch.fnmatch(f, p) for p in dati["pagine"])]
        cartella = dati.get("cartella", f"docs-manuali/{manuale}").rstrip("/") + "/"
        aggiornato = any(f.startswith(cartella) for f in cambiati)
        if toccate and not aggiornato:
            risultato[manuale] = toccate
    return risultato


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 0
    configurazione = tomllib.loads((CARTELLA / "pagine.toml").read_text())
    for manuale, toccate in manuali_da_aggiornare(
        file_cambiati(sys.argv[1]), configurazione
    ).items():
        print(
            f"::warning title=Manuale {manuale}::Sono cambiate pagine descritte dal manuale "
            f"«{manuale}» ({', '.join(toccate)}) ma non il manuale: rifai testo e schermate "
            "(mise run manuali-schermate) se serve."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
