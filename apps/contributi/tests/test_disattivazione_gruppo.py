"""Effetto della disattivazione di un gruppo sul contributo (D-24/A-6/A-10):
respingimento (incluse le APPROVATA), rispetto della riattribuzione D-29,
nessun effetto a campagna LIQUIDATA o senza campagna per l'anno."""

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.bonifici import genera_righe_bonifici
from apps.contributi.disattivazione_gruppo import conta_effetti_disattivazione
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.organizzazione.gruppi import disattiva_gruppo
from apps.organizzazione.models import Gruppo, anno_scout_corrente

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    from apps.accounts.models import Ruolo

    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(
        codice="E0133", nome="AVELLINO 1", iban="IT60X0542811101000000123456"
    )


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def anno() -> int:
    return anno_scout_corrente()


def _campagna(anno, **override) -> Campagna:
    dati = {
        "anno": anno,
        "budget": Decimal("1000.00"),
        "tetto_per_partecipazione": Decimal("50.00"),
        "data_inizio_inserimento": datetime.date(anno - 1, 10, 1),
        "data_fine_inserimento": datetime.date(anno, 9, 30),
    }
    dati.update(override)
    return Campagna.objects.create(**dati)


def _partecipazione(campagna, gruppo, tipologia, codice_socio, **override) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
    dati = {
        "campagna": campagna,
        "capo": capo,
        "gruppo": gruppo,
        "tipologia": tipologia,
        "data_inizio": datetime.date(campagna.anno, 6, 1),
        "data_fine": datetime.date(campagna.anno, 6, 8),
        "luogo": "Base scout",
        "quota_versata": Decimal("51.50"),
    }
    dati.update(override)
    p = Partecipazione(**dati)
    p.full_clean(exclude=["stato"])
    p.save()
    return p


class TestRespingiPerDisattivazione:
    def test_respinge_approvata_con_causale(self, segreteria, gruppo, cfm, anno):
        campagna = _campagna(anno)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        p = _partecipazione(campagna, gruppo, cfm, "10001", stato=StatoPartecipazione.APPROVATA)

        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")

        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.RESPINTA
        assert p.motivazione_respingimento == "Gruppo non più attivo"

    def test_non_tocca_partecipazione_gia_riattribuita(self, segreteria, gruppo, cfm, anno):
        altro_gruppo = Gruppo.objects.create(codice="E0199", nome="ALTRO")
        campagna = _campagna(anno)
        p = _partecipazione(campagna, altro_gruppo, cfm, "10001")

        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")

        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.INSERITA

    def test_nessun_effetto_se_campagna_liquidata(self, segreteria, gruppo, cfm, anno):
        campagna = _campagna(anno)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.LIQUIDATA)
        p = _partecipazione(campagna, gruppo, cfm, "10001", stato=StatoPartecipazione.APPROVATA)

        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")

        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.APPROVATA

    def test_nessuna_campagna_per_anno_non_solleva(self, segreteria, gruppo):
        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")  # non deve sollevare


class TestContaEffettiDisattivazione:
    def test_conteggi(self, gruppo, cfm, anno):
        altro_gruppo = Gruppo.objects.create(codice="E0199", nome="ALTRO")
        campagna = _campagna(anno)
        _partecipazione(campagna, gruppo, cfm, "10001")
        _partecipazione(campagna, altro_gruppo, cfm, "10002")

        conteggi = conta_effetti_disattivazione(gruppo, anno)

        assert conteggi["verranno_respinte"] == 1


class TestGeneraBonificiEsclusioneGruppoDisattivato:
    def test_gruppo_disattivato_dopo_chiusura_escluso(self, segreteria, gruppo, cfm, anno):
        campagna = _campagna(anno)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.CHIUSA)
        campagna.refresh_from_db()
        p = _partecipazione(campagna, gruppo, cfm, "10001", stato=StatoPartecipazione.APPROVATA)
        ContributoPartecipazione.objects.create(
            partecipazione=p, importo=Decimal("50.00"), is_simulazione=False
        )

        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")

        righe = genera_righe_bonifici(campagna, causale="Test")
        assert righe == []
