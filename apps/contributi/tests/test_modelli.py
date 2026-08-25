"""Vincoli strutturali dei modelli di contributi (D-10, D-12, D-22, D-24)."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from apps.anagrafica.models import Capo
from apps.contributi.models import Campagna, Partecipazione, StatoPartecipazione, TipologiaCampo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=2026,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2026, 1, 1),
        data_fine_inserimento=datetime.date(2026, 8, 31),
    )


@pytest.fixture
def tipologia() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


def _partecipazione(campagna, capo, gruppo, tipologia, **override) -> Partecipazione:
    dati = {
        "campagna": campagna,
        "capo": capo,
        "gruppo": gruppo,
        "tipologia": tipologia,
        "data_inizio": datetime.date(2026, 6, 1),
        "data_fine": datetime.date(2026, 6, 8),
        "luogo": "Base scout",
        "quota_versata": Decimal("51.50"),
    }
    dati.update(override)
    return Partecipazione(**dati)


class TestCampagna:
    def test_data_fine_precedente_a_inizio_rifiutata(self):
        campagna = Campagna(
            anno=2027,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2027, 6, 1),
            data_fine_inserimento=datetime.date(2027, 1, 1),
        )
        with pytest.raises(ValidationError):
            campagna.full_clean(exclude=["stato"])

    def test_finestra_associativa(self, campagna):
        inizio, fine = campagna.finestra_associativa
        assert inizio == datetime.date(2025, 10, 1)
        assert fine == datetime.date(2026, 9, 30)

    def test_stato_protetto_da_riassegnazione_diretta(self, campagna):
        with pytest.raises(AttributeError):
            campagna.stato = "CHIUSA"


class TestPartecipazione:
    def test_respinta_senza_causale_rifiutata(self, campagna, capo, gruppo, tipologia):
        partecipazione = _partecipazione(
            campagna, capo, gruppo, tipologia, stato=StatoPartecipazione.RESPINTA
        )
        with pytest.raises(ValidationError):
            partecipazione.full_clean(exclude=["stato"])

    def test_respinta_con_causale_valida(self, campagna, capo, gruppo, tipologia):
        partecipazione = _partecipazione(
            campagna,
            capo,
            gruppo,
            tipologia,
            stato=StatoPartecipazione.RESPINTA,
            motivazione_respingimento="Documentazione insufficiente.",
        )
        partecipazione.full_clean(exclude=["stato"])  # non deve sollevare

    def test_data_inizio_fuori_dalla_finestra_associativa_rifiutata(
        self, campagna, capo, gruppo, tipologia
    ):
        partecipazione = _partecipazione(
            campagna, capo, gruppo, tipologia, data_inizio=datetime.date(2024, 1, 1)
        )
        with pytest.raises(ValidationError):
            partecipazione.full_clean(exclude=["stato"])

    def test_capo_protetto_da_cancellazione(self, campagna, capo, gruppo, tipologia):
        partecipazione = _partecipazione(campagna, capo, gruppo, tipologia)
        partecipazione.full_clean(exclude=["stato"])
        partecipazione.save()

        with pytest.raises(ProtectedError):
            capo.delete()

    def test_chiave_logica_univoca(self, campagna, capo, gruppo, tipologia):
        _partecipazione(campagna, capo, gruppo, tipologia).save()
        with pytest.raises(ValidationError):
            _partecipazione(campagna, capo, gruppo, tipologia, luogo="Altra base").full_clean(
                exclude=["stato"]
            )

    def test_stato_protetto_da_riassegnazione_diretta(self, campagna, capo, gruppo, tipologia):
        partecipazione = _partecipazione(campagna, capo, gruppo, tipologia)
        partecipazione.save()
        with pytest.raises(AttributeError):
            partecipazione.stato = StatoPartecipazione.APPROVATA

    def test_tipologia_altro_senza_descrizione_rifiutata(self, campagna, capo, gruppo):
        tipologia_altro = TipologiaCampo.objects.get(codice="ALTRO")
        partecipazione = _partecipazione(campagna, capo, gruppo, tipologia_altro)
        with pytest.raises(ValidationError):
            partecipazione.full_clean(exclude=["stato"])

    def test_tipologia_altro_con_descrizione_valida(self, campagna, capo, gruppo):
        tipologia_altro = TipologiaCampo.objects.get(codice="ALTRO")
        partecipazione = _partecipazione(
            campagna,
            capo,
            gruppo,
            tipologia_altro,
            descrizione_altro="Campo di specialità",
            quota_versata=Decimal("30.00"),
        )
        partecipazione.full_clean(exclude=["stato"])  # non deve sollevare

    def test_tipologia_diversa_da_altro_non_richiede_descrizione(
        self, campagna, capo, gruppo, tipologia
    ):
        partecipazione = _partecipazione(campagna, capo, gruppo, tipologia)
        partecipazione.full_clean(exclude=["stato"])  # non deve sollevare


class TestTipologiaCampoSeed:
    def test_cfm_cfa_ccg_seminate(self):
        codici = set(TipologiaCampo.objects.values_list("codice", flat=True))
        assert {"CFM", "CFA", "CCG"} <= codici
        cfm = TipologiaCampo.objects.get(codice="CFM")
        assert cfm.approvazione_automatica is True
        assert cfm.quota_default == Decimal("51.50")

    def test_altro_seminata(self):
        altro = TipologiaCampo.objects.get(codice="ALTRO")
        assert altro.approvazione_automatica is False
        assert altro.quota_default is None
