"""Visibilità post-chiusura (D-13): totali degli altri gruppi per un
account di gruppo, nulla per i ruoli Zona (già vedono tutto), mai IBAN."""

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.contributi.visibilita import TotaleGruppo, totali_altri_gruppi
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def gruppo_a() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def gruppo_b() -> Gruppo:
    return Gruppo.objects.create(codice="E0199", nome="AVELLINO 2")


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def cg_a(gruppo_a) -> Utente:
    utente = _persona("cg-a@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
    return utente


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


def _campagna(anno, stato, **override) -> Campagna:
    dati = {
        "anno": anno,
        "budget": Decimal("1000.00"),
        "tetto_per_partecipazione": Decimal("50.00"),
        "data_inizio_inserimento": datetime.date(anno - 1, 10, 1),
        "data_fine_inserimento": datetime.date(anno, 9, 30),
    }
    dati.update(override)
    c = Campagna.objects.create(**dati)
    Campagna.objects.filter(pk=c.pk).update(stato=stato)
    c.refresh_from_db()
    return c


def _partecipazione_congelata(campagna, gruppo, tipologia, codice_socio, importo) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
    p = Partecipazione(
        campagna=campagna,
        capo=capo,
        gruppo=gruppo,
        tipologia=tipologia,
        data_inizio=datetime.date(campagna.anno, 6, 1),
        data_fine=datetime.date(campagna.anno, 6, 8),
        luogo="Base scout",
        quota_versata=Decimal("51.50"),
        stato=StatoPartecipazione.APPROVATA,
    )
    p.full_clean(exclude=["stato"])
    p.save()
    ContributoPartecipazione.objects.create(partecipazione=p, importo=importo, is_simulazione=False)
    return p


class TestTotaliAltriGruppi:
    def test_vuota_pre_chiusura(self, cg_a, gruppo_a, gruppo_b, cfm):
        campagna = _campagna(2026, StatoCampagna.IN_VALUTAZIONE)
        _partecipazione_congelata(campagna, gruppo_b, cfm, "10001", Decimal("50.00"))
        assert totali_altri_gruppi(cg_a, campagna) == []

    def test_vuota_per_ruolo_zona(self, segreteria, gruppo_a, gruppo_b, cfm):
        campagna = _campagna(2027, StatoCampagna.CHIUSA)
        _partecipazione_congelata(campagna, gruppo_a, cfm, "10001", Decimal("50.00"))
        _partecipazione_congelata(campagna, gruppo_b, cfm, "10002", Decimal("30.00"))
        assert totali_altri_gruppi(segreteria, campagna) == []

    def test_cg_vede_solo_gli_altri_gruppi(self, cg_a, gruppo_a, gruppo_b, cfm):
        campagna = _campagna(2028, StatoCampagna.CHIUSA)
        _partecipazione_congelata(campagna, gruppo_a, cfm, "10001", Decimal("50.00"))
        _partecipazione_congelata(campagna, gruppo_b, cfm, "10002", Decimal("30.00"))

        totali = totali_altri_gruppi(cg_a, campagna)

        assert len(totali) == 1
        assert totali[0].gruppo_codice == "E0199"
        assert totali[0].importo == Decimal("30.00")

    def test_nessun_iban_nel_dataclass(self):
        assert not hasattr(TotaleGruppo, "iban")
        assert not hasattr(TotaleGruppo, "intestazione_conto")
        campi = {f.name for f in TotaleGruppo.__dataclass_fields__.values()}
        assert "iban" not in campi
        assert "intestazione_conto" not in campi
