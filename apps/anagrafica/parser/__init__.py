"""Parser dei file prodotti dai sistemi associativi AGESCI.

- `autorizzazioni`: PDF di autorizzazione unità dei gruppi.
- Il parsing del CSV "Ricerca Soci" di Buona Caccia vive in `buonacaccia.py`
  (da implementare in M2).
"""

from .autorizzazioni import ParseResult, parse_pdf, parse_year

__all__ = ["ParseResult", "parse_pdf", "parse_year"]
