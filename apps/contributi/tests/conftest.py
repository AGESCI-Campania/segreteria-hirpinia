import datetime

import pytest

from apps.contributi.models import Campagna

# Un giorno dentro la finestra di inserimento delle fixture `campagna`
# (2025-10-01 – 2026-09-30, anno scout 2026).
OGGI_IN_FINESTRA = datetime.date(2026, 6, 15)


@pytest.fixture
def finestra_inserimento_aperta(monkeypatch):
    """Fissa a OGGI_IN_FINESTRA la data di riferimento di
    `Campagna.in_finestra_inserimento()` quando non ne riceve una esplicita:
    senza, i test con la finestra fissa dell'anno scout 2026 fallivano appena
    superato il 2026-09-30.

    Si sostituisce solo il default di questo metodo, non
    `timezone.localdate`: `Ruolo.data_inizio`/`Delega.data_inizio` hanno
    `default=timezone.localdate` (la funzione originale) e con una data
    globale fissa i ruoli creati nei test risulterebbero non ancora attivi.
    Il confronto con la finestra resta quello reale."""
    originale = Campagna.in_finestra_inserimento

    def in_finestra_inserimento(self, alla_data=None):
        return originale(self, alla_data or OGGI_IN_FINESTRA)

    monkeypatch.setattr(Campagna, "in_finestra_inserimento", in_finestra_inserimento)
