"""Calcolo del contributo (D-10): casi limite esplicitamente richiesti da
CLAUDE.md — divisione non esatta, tetto raggiunto, quota_versata inferiore al
proporzionale, N=0, budget nullo."""

import datetime
from decimal import Decimal

import pytest

from apps.anagrafica.models import Capo
from apps.contributi.calcolo import calcola_importi
from apps.contributi.models import Campagna, Partecipazione, StatoPartecipazione, TipologiaCampo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def tipologia() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


def _campagna(**override) -> Campagna:
    dati = {
        "anno": 2026,
        "budget": Decimal("1000.00"),
        "tetto_per_partecipazione": Decimal("50.00"),
        "data_inizio_inserimento": datetime.date(2026, 1, 1),
        "data_fine_inserimento": datetime.date(2026, 8, 31),
    }
    dati.update(override)
    return Campagna.objects.create(**dati)


def _partecipazione_approvata(
    n: int, campagna, gruppo, tipologia, *, quota_versata: Decimal
) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=f"1{n:04d}", nome="MARIO", cognome=f"ROSSI{n}")
    partecipazione = Partecipazione(
        campagna=campagna,
        capo=capo,
        gruppo=gruppo,
        tipologia=tipologia,
        data_inizio=datetime.date(2026, 6, 1),
        data_fine=datetime.date(2026, 6, 8),
        luogo="Base scout",
        quota_versata=quota_versata,
        stato=StatoPartecipazione.APPROVATA,
    )
    partecipazione.full_clean(exclude=["stato"])
    partecipazione.save()
    return partecipazione


class TestCalcolaImporti:
    def test_divisione_non_esatta_1000_su_30(self, gruppo, tipologia):
        campagna = _campagna(budget=Decimal("1000.00"), tetto_per_partecipazione=Decimal("100.00"))
        for n in range(30):
            _partecipazione_approvata(
                n, campagna, gruppo, tipologia, quota_versata=Decimal("100.00")
            )

        risultato = calcola_importi(campagna)

        assert risultato.n == 30
        assert all(importo == Decimal("33.33") for importo in risultato.importi.values())
        totale = sum(risultato.importi.values(), Decimal("0"))
        assert totale <= campagna.budget
        assert risultato.residuo == campagna.budget - totale
        assert risultato.residuo == Decimal("0.10")

    def test_tetto_per_partecipazione_raggiunto(self, gruppo, tipologia):
        campagna = _campagna(budget=Decimal("1000.00"), tetto_per_partecipazione=Decimal("50.00"))
        _partecipazione_approvata(0, campagna, gruppo, tipologia, quota_versata=Decimal("100.00"))

        risultato = calcola_importi(campagna)

        (importo,) = risultato.importi.values()
        assert importo == Decimal("50.00")

    def test_quota_versata_inferiore_al_proporzionale(self, gruppo, tipologia):
        campagna = _campagna(budget=Decimal("1000.00"), tetto_per_partecipazione=Decimal("1000.00"))
        _partecipazione_approvata(0, campagna, gruppo, tipologia, quota_versata=Decimal("30.00"))
        _partecipazione_approvata(1, campagna, gruppo, tipologia, quota_versata=Decimal("30.00"))

        risultato = calcola_importi(campagna)

        assert all(importo == Decimal("30.00") for importo in risultato.importi.values())

    def test_n_zero(self, gruppo, tipologia):
        campagna = _campagna(budget=Decimal("500.00"))

        risultato = calcola_importi(campagna)

        assert risultato.n == 0
        assert risultato.quota_proporzionale == Decimal("500.00")
        assert risultato.residuo == Decimal("500.00")
        assert risultato.importi == {}

    def test_budget_nullo(self, gruppo, tipologia):
        campagna = _campagna(budget=Decimal("0.00"), tetto_per_partecipazione=Decimal("50.00"))
        _partecipazione_approvata(0, campagna, gruppo, tipologia, quota_versata=Decimal("51.50"))
        _partecipazione_approvata(1, campagna, gruppo, tipologia, quota_versata=Decimal("51.50"))

        risultato = calcola_importi(campagna)

        assert risultato.quota_proporzionale == Decimal("0")
        assert all(importo == Decimal("0.00") for importo in risultato.importi.values())
        assert risultato.residuo == Decimal("0.00")
