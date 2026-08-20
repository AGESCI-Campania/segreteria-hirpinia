"""Simulazione del calcolo (D-16): ripetibile, nessuna scrittura sugli
importi definitivi."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    Partecipazione,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.contributi.simulazione import simula_calcolo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=2026,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2026, 1, 1),
        data_fine_inserimento=datetime.date(2026, 8, 31),
    )


def _partecipazione_approvata(campagna, gruppo, tipologia, codice_socio) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
    p = Partecipazione(
        campagna=campagna,
        capo=capo,
        gruppo=gruppo,
        tipologia=tipologia,
        data_inizio=datetime.date(2026, 6, 1),
        data_fine=datetime.date(2026, 6, 8),
        luogo="Base scout",
        quota_versata=Decimal("51.50"),
        stato=StatoPartecipazione.APPROVATA,
    )
    p.full_clean(exclude=["stato"])
    p.save()
    return p


class TestSimulaCalcolo:
    def test_richiede_ruolo(self, campagna):
        estraneo = _persona("estraneo@campania.agesci.it")
        with pytest.raises(PermissionDenied):
            simula_calcolo(utente=estraneo, campagna=campagna)

    def test_scrive_righe_simulazione(self, segreteria, campagna, gruppo, cfm):
        p = _partecipazione_approvata(campagna, gruppo, cfm, "10001")

        risultato = simula_calcolo(utente=segreteria, campagna=campagna)

        assert risultato.n == 1
        riga = ContributoPartecipazione.objects.get(partecipazione=p)
        assert riga.is_simulazione is True
        assert riga.importo == Decimal("50.00")

    def test_seconda_esecuzione_sostituisce_la_prima(self, segreteria, campagna, gruppo, cfm):
        p1 = _partecipazione_approvata(campagna, gruppo, cfm, "10001")
        simula_calcolo(utente=segreteria, campagna=campagna)
        assert ContributoPartecipazione.objects.filter(is_simulazione=True).count() == 1

        p2 = _partecipazione_approvata(campagna, gruppo, cfm, "10002")
        simula_calcolo(utente=segreteria, campagna=campagna)

        righe = ContributoPartecipazione.objects.filter(is_simulazione=True)
        assert righe.count() == 2
        assert set(righe.values_list("partecipazione_id", flat=True)) == {p1.pk, p2.pk}

    def test_non_scrive_righe_definitive(self, segreteria, campagna, gruppo, cfm):
        _partecipazione_approvata(campagna, gruppo, cfm, "10001")

        simula_calcolo(utente=segreteria, campagna=campagna)

        assert not ContributoPartecipazione.objects.filter(is_simulazione=False).exists()
