"""Riepilogo di campagna (D-13): N/quota/residuo, blocco fuori da
CHIUSA/LIQUIDATA, N stabile dopo una disattivazione di gruppo post-chiusura."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

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
from apps.contributi.riepilogo import calcola_riepilogo
from apps.organizzazione.gruppi import disattiva_gruppo
from apps.organizzazione.models import Gruppo, anno_scout_corrente

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
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


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


class TestCalcolaRiepilogo:
    def test_blocca_fuori_da_chiusa_liquidata(self):
        campagna = _campagna(2030, StatoCampagna.IN_VALUTAZIONE)
        with pytest.raises(ValidationError):
            calcola_riepilogo(campagna)

    def test_n_quota_residuo(self, cfm):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        campagna = _campagna(2031, StatoCampagna.CHIUSA)
        _partecipazione_congelata(campagna, gruppo, cfm, "10001", Decimal("50.00"))
        _partecipazione_congelata(campagna, gruppo, cfm, "10002", Decimal("30.00"))

        riepilogo = calcola_riepilogo(campagna)

        assert riepilogo.n == 2
        assert riepilogo.quota_proporzionale == Decimal("500.00")
        assert riepilogo.residuo == Decimal("920.00")
        assert len(riepilogo.righe) == 1
        assert riepilogo.righe[0].importo == Decimal("80.00")

    def test_n_stabile_dopo_disattivazione_post_chiusura(self, segreteria, cfm):
        anno = anno_scout_corrente()
        gruppo = Gruppo.objects.create(codice="E0199", nome="ALTRO GRUPPO")
        campagna = _campagna(anno, StatoCampagna.CHIUSA)
        _partecipazione_congelata(campagna, gruppo, cfm, "10001", Decimal("50.00"))

        riepilogo_prima = calcola_riepilogo(campagna)
        assert riepilogo_prima.n == 1

        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")

        riepilogo_dopo = calcola_riepilogo(campagna)
        assert riepilogo_dopo.n == 1  # invariato: N è dalle righe congelate
        assert riepilogo_dopo.quota_proporzionale == riepilogo_prima.quota_proporzionale
        assert riepilogo_dopo.righe == []  # ma il gruppo non compare più fra le righe pagate
        assert riepilogo_dopo.residuo == campagna.budget  # tutto torna al residuo
