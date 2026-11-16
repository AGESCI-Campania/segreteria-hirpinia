import datetime

import pytest

from apps.assemblee import sedute

# Un giorno successivo alle date delle sedute delle fixture (al più 2027-04-10).
OGGI_DOPO_LE_SEDUTE = datetime.date(2027, 12, 31)


@pytest.fixture(autouse=True)
def sedute_apribili(monkeypatch):
    """Fissa a OGGI_DOPO_LE_SEDUTE il giorno di riferimento di
    `sedute.puo_aprire_oggi()` quando non ne riceve uno esplicito: senza, i
    test che aprono una seduta con data fissa fallirebbero finché quella data
    non è passata. Il confronto con la data della seduta resta quello reale."""
    originale = sedute.puo_aprire_oggi

    def puo_aprire_oggi(seduta, oggi=None):
        return originale(seduta, oggi or OGGI_DOPO_LE_SEDUTE)

    monkeypatch.setattr(sedute, "puo_aprire_oggi", puo_aprire_oggi)
