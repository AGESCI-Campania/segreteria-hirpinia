"""Parser dei file prodotti dai sistemi associativi AGESCI.

- `autorizzazioni`: PDF di autorizzazione unità dei gruppi.
- `buonacaccia`: CSV "Ricerca Soci" di Buona Caccia.
"""

from .autorizzazioni import ParseResult, parse_pdf, parse_year
from .buonacaccia import AnomaliaRiga, RigaBuonaCaccia, RisultatoParsing, parse_csv

__all__ = [
    "ParseResult",
    "parse_pdf",
    "parse_year",
    "AnomaliaRiga",
    "RigaBuonaCaccia",
    "RisultatoParsing",
    "parse_csv",
]
