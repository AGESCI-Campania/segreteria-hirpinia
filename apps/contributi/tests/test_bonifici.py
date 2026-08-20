"""Generazione del file bonifici (D-14): somma per gruppo corrente, esclusione
gruppi a importo zero, blocco prima del congelamento, riattribuzione D-29
post-chiusura."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.anagrafica.models import Capo, CensimentoCapo, TrasferimentoCapo
from apps.contributi.bonifici import genera_righe_bonifici
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.contributi.trasferimenti import riattribuisci_partecipazioni
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


@pytest.fixture
def gruppo_a() -> Gruppo:
    return Gruppo.objects.create(
        codice="E0133", nome="AVELLINO 1", iban="IT60X0542811101000000123456"
    )


@pytest.fixture
def gruppo_b() -> Gruppo:
    return Gruppo.objects.create(codice="E0199", nome="AVELLINO 2")


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def campagna() -> Campagna:
    c = Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )
    Campagna.objects.filter(pk=c.pk).update(stato=StatoCampagna.CHIUSA)
    c.refresh_from_db()
    return c


def _partecipazione_con_importo(
    n: int, campagna, gruppo, tipologia, importo: Decimal, *, is_simulazione=False
) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=f"1{n:04d}", nome="MARIO", cognome=f"ROSSI{n}")
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
    ContributoPartecipazione.objects.create(
        partecipazione=p, importo=importo, is_simulazione=is_simulazione
    )
    return p


class TestGeneraRigheBonifici:
    def test_blocca_se_non_chiusa_o_liquidata(self, gruppo_a, cfm):
        campagna_aperta = Campagna.objects.create(
            anno=2027,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2026, 10, 1),
            data_fine_inserimento=datetime.date(2027, 9, 30),
        )
        with pytest.raises(ValidationError):
            genera_righe_bonifici(campagna_aperta, causale="Test")

    def test_somma_piu_partecipazioni_stesso_gruppo(self, campagna, gruppo_a, cfm):
        _partecipazione_con_importo(0, campagna, gruppo_a, cfm, Decimal("50.00"))
        _partecipazione_con_importo(1, campagna, gruppo_a, cfm, Decimal("30.00"))

        righe = genera_righe_bonifici(campagna, causale="Contributo FoCa 2026")

        assert len(righe) == 1
        assert righe[0].gruppo_codice == "E0133"
        assert righe[0].importo == Decimal("80.00")
        assert righe[0].iban == "IT60X0542811101000000123456"
        assert righe[0].causale == "Contributo FoCa 2026"

    def test_esclude_gruppo_a_importo_zero(self, campagna, gruppo_a, gruppo_b, cfm):
        _partecipazione_con_importo(0, campagna, gruppo_a, cfm, Decimal("50.00"))
        _partecipazione_con_importo(1, campagna, gruppo_b, cfm, Decimal("0.00"))

        righe = genera_righe_bonifici(campagna, causale="Test")

        codici = {r.gruppo_codice for r in righe}
        assert codici == {"E0133"}

    def test_ignora_righe_di_simulazione(self, campagna, gruppo_a, cfm):
        _partecipazione_con_importo(
            0, campagna, gruppo_a, cfm, Decimal("999.00"), is_simulazione=True
        )

        righe = genera_righe_bonifici(campagna, causale="Test")

        assert righe == []

    def test_riattribuzione_post_chiusura_sposta_la_riga(self, campagna, gruppo_a, gruppo_b, cfm):
        capo = Capo.objects.create(codice_socio="19001", nome="ANNA", cognome="VERDI")
        CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO, gruppo=gruppo_a)
        p = Partecipazione(
            campagna=campagna,
            capo=capo,
            gruppo=gruppo_a,
            tipologia=cfm,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base scout",
            quota_versata=Decimal("51.50"),
            stato=StatoPartecipazione.APPROVATA,
        )
        p.full_clean(exclude=["stato"])
        p.save()
        ContributoPartecipazione.objects.create(
            partecipazione=p, importo=Decimal("50.00"), is_simulazione=False
        )

        righe_prima = genera_righe_bonifici(campagna, causale="Test")
        assert {r.gruppo_codice for r in righe_prima} == {"E0133"}

        trasferimento = TrasferimentoCapo.objects.create(
            capo=capo, anno_scout=ANNO, gruppo_origine=gruppo_a, gruppo_destino=gruppo_b
        )
        riattribuisci_partecipazioni(trasferimento)

        righe_dopo = genera_righe_bonifici(campagna, causale="Test")
        assert {r.gruppo_codice for r in righe_dopo} == {"E0199"}
