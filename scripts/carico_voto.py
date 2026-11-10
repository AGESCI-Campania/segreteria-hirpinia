"""Prova di carico del voto elettronico (docs/plan_voto.md, V6). Solo stdlib.

Ogni votante simulato apre /voto/, entra con il proprio codice, fa qualche
giro di polling, apre la scheda, rivede e conferma. I codici vengono da
`manage.py prova_carico_voto prepara`. Criteri: p95 sotto 500 ms, nessun
errore, schede = votanti (verificato a parte con `prova_carico_voto verifica`).

    python scripts/carico_voto.py http://[::1]:8765 /tmp/codici.txt --host localhost:8765
"""

from __future__ import annotations

import argparse
import http.cookiejar
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

SOGLIA_P95_MS = 500


class Votante:
    def __init__(self, base: str, host: str | None, codice: str, giri_polling: int):
        self.base = base.rstrip("/")
        self.host = host
        self.codice = codice
        self.giri_polling = giri_polling
        self.cookie = http.cookiejar.CookieJar()
        self.apri = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie)
        ).open
        self.tempi: dict[str, list[float]] = defaultdict(list)

    def _richiesta(self, nome: str, percorso: str, dati: dict | None = None) -> str:
        url = self.base + percorso
        intestazioni = {"Referer": url}
        if self.host:
            intestazioni["Host"] = self.host
        corpo = None
        if dati is not None:
            dati = {**dati, "csrfmiddlewaretoken": self._csrf()}
            corpo = urllib.parse.urlencode(dati, doseq=True).encode()
        inizio = time.perf_counter()
        with self.apri(
            urllib.request.Request(url, data=corpo, headers=intestazioni), timeout=30
        ) as r:
            testo = r.read().decode("utf-8", "replace")
        self.tempi[nome].append((time.perf_counter() - inizio) * 1000)
        return testo

    def _csrf(self) -> str:
        return next(c.value for c in self.cookie if c.name == "csrftoken")

    def vota(self) -> None:
        self._richiesta("pagina", "/voto/")
        self._richiesta("accesso", "/voto/accedi/", {"codice": self.codice})
        for _ in range(self.giri_polling):
            self._richiesta("polling", "/voto/stato.json")
        scheda = self._richiesta("scheda", "/voto/scheda/")
        votazione = re.search(r'name="votazione" value="(\d+)"', scheda)
        candidato = re.search(r'name="candidati_0" value="(\d+)"', scheda)
        if not votazione or not candidato:
            raise RuntimeError("scheda non trovata")
        dati = {
            "votazione": votazione.group(1),
            "candidati_0": candidato.group(1),
            "esito_0": "VOTO",
        }
        self._richiesta("rivedi", "/voto/scheda/", {**dati, "azione": "rivedi"})
        ricevuta = self._richiesta("conferma", "/voto/scheda/", {**dati, "azione": "conferma"})
        if "Voto registrato" not in ricevuta:
            raise RuntimeError("voto non registrato")


def percentile(valori: list[float], p: float) -> float:
    valori = sorted(valori)
    return valori[min(len(valori) - 1, int(round(p / 100 * (len(valori) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("codici")
    parser.add_argument("--host", help="Intestazione Host da inviare (es. localhost:8765).")
    parser.add_argument("--concorrenza", type=int, default=200)
    parser.add_argument("--polling", type=int, default=5, help="Giri di polling per votante.")
    argomenti = parser.parse_args()

    codici = [r.strip() for r in open(argomenti.codici, encoding="utf-8") if r.strip()]
    votanti = [Votante(argomenti.base, argomenti.host, c, argomenti.polling) for c in codici]
    errori: list[str] = []

    def esegui(votante: Votante) -> None:
        try:
            votante.vota()
        except Exception as errore:  # noqa: BLE001 - si contano tutti gli errori
            errori.append(f"{type(errore).__name__}: {errore}")

    inizio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=argomenti.concorrenza) as pool:
        list(pool.map(esegui, votanti))
    durata = time.perf_counter() - inizio

    tempi: dict[str, list[float]] = defaultdict(list)
    for votante in votanti:
        for nome, valori in votante.tempi.items():
            tempi[nome].extend(valori)
    tutti = [t for valori in tempi.values() for t in valori]
    print(f"{len(votanti)} votanti, concorrenza {argomenti.concorrenza}, durata {durata:.1f} s")
    print(f"{len(tutti)} richieste, {len(tutti) / durata:.1f} req/s, errori {len(errori)}")
    for nome, valori in sorted(tempi.items()):
        print(
            f"  {nome:9} n={len(valori):5}  p50={statistics.median(valori):6.0f} ms  "
            f"p95={percentile(valori, 95):6.0f} ms  max={max(valori):6.0f} ms"
        )
    p95 = percentile(tutti, 95) if tutti else float("inf")
    print(f"p95 complessivo {p95:.0f} ms (soglia {SOGLIA_P95_MS} ms)")
    for errore in sorted(set(errori))[:10]:
        print(f"  errore: {errore}")
    return 0 if not errori and p95 < SOGLIA_P95_MS else 1


if __name__ == "__main__":
    sys.exit(main())
