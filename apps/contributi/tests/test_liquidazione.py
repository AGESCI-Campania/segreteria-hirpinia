"""Liquidazione campagna (CHIUSA→LIQUIDATA, D-12, D-14): blocco fuori stato,
campi obbligatori, transizione, preclusione in impersonificazione."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.contributi.campagne import liquida_campagna
from apps.contributi.models import Campagna, StatoCampagna

pytestmark = pytest.mark.django_db


class FakeSession(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeRequest:
    def __init__(self, session=None):
        self.session = FakeSession(session or {})


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def campagna_chiusa() -> Campagna:
    c = Campagna.objects.create(
        anno=2026,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )
    Campagna.objects.filter(pk=c.pk).update(stato=StatoCampagna.CHIUSA)
    c.refresh_from_db()
    return c


class TestLiquidaCampagna:
    def test_blocca_se_non_chiusa(self, segreteria):
        campagna = Campagna.objects.create(
            anno=2027,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2026, 10, 1),
            data_fine_inserimento=datetime.date(2027, 9, 30),
        )
        with pytest.raises(ValidationError):
            liquida_campagna(
                FakeRequest(),
                utente=segreteria,
                campagna=campagna,
                data_liquidazione=datetime.date(2027, 9, 25),
                riferimento_bonifico="Distinta 1",
            )

    def test_blocca_su_riferimento_vuoto(self, segreteria, campagna_chiusa):
        with pytest.raises(ValidationError):
            liquida_campagna(
                FakeRequest(),
                utente=segreteria,
                campagna=campagna_chiusa,
                data_liquidazione=datetime.date(2026, 9, 25),
                riferimento_bonifico="   ",
            )

    def test_liquida_correttamente(self, segreteria, campagna_chiusa):
        liquida_campagna(
            FakeRequest(),
            utente=segreteria,
            campagna=campagna_chiusa,
            data_liquidazione=datetime.date(2026, 9, 25),
            riferimento_bonifico="Distinta n. 42",
        )

        campagna_chiusa.refresh_from_db()
        assert campagna_chiusa.stato == StatoCampagna.LIQUIDATA
        assert campagna_chiusa.riferimento_bonifico == "Distinta n. 42"
        assert timezone.localtime(campagna_chiusa.liquidata_il).date() == datetime.date(2026, 9, 25)

    def test_preclusa_in_impersonificazione(self, segreteria, campagna_chiusa):
        request = FakeRequest(session={"hijack_history": ["1"]})
        with pytest.raises(PermissionDenied):
            liquida_campagna(
                request,
                utente=segreteria,
                campagna=campagna_chiusa,
                data_liquidazione=datetime.date(2026, 9, 25),
                riferimento_bonifico="Distinta n. 42",
            )
        campagna_chiusa.refresh_from_db()
        assert campagna_chiusa.stato == StatoCampagna.CHIUSA
