"""Transizioni FSM di Campagna con effetti di dominio (D-12): avvio
valutazione (auto-approvazione CFM/CFA/CCG) e chiusura (gate partecipazioni
pendenti, gate IBAN D-14, congelamento importi)."""

import datetime
from decimal import Decimal

import pytest
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.campagne import avvia_valutazione, chiudi_campagna
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    LivelloCampo,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

IBAN_VALIDO = "IT60X0542811101000000123456"


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
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def altro() -> TipologiaCampo:
    return TipologiaCampo.objects.create(
        codice="ALTRO", nome="Altro", approvazione_automatica=False, livello=LivelloCampo.ZONA
    )


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=2026,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2026, 1, 1),
        data_fine_inserimento=datetime.date(2026, 8, 31),
    )


def _capo(n: int) -> Capo:
    return Capo.objects.create(codice_socio=f"1{n:04d}", nome="MARIO", cognome=f"ROSSI{n}")


def _partecipazione(campagna, gruppo, tipologia, capo, **override) -> Partecipazione:
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
    p = Partecipazione(**dati)
    p.full_clean(exclude=["stato"])
    p.save()
    return p


class TestAvviaValutazione:
    def test_richiede_ruolo(self, campagna):
        utente = _persona("senza-ruolo@campania.agesci.it")
        with pytest.raises(PermissionDenied):
            avvia_valutazione(utente=utente, campagna=campagna)

    def test_richiede_stato_aperta(self, segreteria, campagna):
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        campagna.refresh_from_db()
        with pytest.raises(ValidationError):
            avvia_valutazione(utente=segreteria, campagna=campagna)

    def test_auto_approva_cfm_lascia_altro_inserita(self, segreteria, campagna, gruppo, cfm, altro):
        p_cfm = _partecipazione(campagna, gruppo, cfm, _capo(0))
        p_altro = _partecipazione(campagna, gruppo, altro, _capo(1))

        avvia_valutazione(utente=segreteria, campagna=campagna)

        campagna.refresh_from_db()
        p_cfm.refresh_from_db()
        p_altro.refresh_from_db()
        assert campagna.stato == StatoCampagna.IN_VALUTAZIONE
        assert p_cfm.stato == StatoPartecipazione.APPROVATA
        assert p_cfm.valutata_da_id == segreteria.pk
        assert p_altro.stato == StatoPartecipazione.INSERITA


class TestChiudiCampagna:
    def test_richiede_stato_in_valutazione(self, segreteria, campagna):
        with pytest.raises(ValidationError):
            chiudi_campagna(FakeRequest(), utente=segreteria, campagna=campagna)

    def test_blocca_su_partecipazioni_pendenti(self, segreteria, campagna, gruppo, cfm):
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        campagna.refresh_from_db()
        _partecipazione(campagna, gruppo, cfm, _capo(0))  # resta INSERITA

        with pytest.raises(ValidationError):
            chiudi_campagna(FakeRequest(), utente=segreteria, campagna=campagna)

    def test_blocca_su_iban_mancante(self, segreteria, campagna, gruppo, cfm):
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        campagna.refresh_from_db()
        _partecipazione(campagna, gruppo, cfm, _capo(0), stato=StatoPartecipazione.APPROVATA)

        with pytest.raises(ValidationError):
            chiudi_campagna(FakeRequest(), utente=segreteria, campagna=campagna)

    def test_congela_importi_e_ripulisce_simulazione(self, segreteria, campagna, gruppo, cfm):
        Gruppo.objects.filter(pk=gruppo.pk).update(iban=IBAN_VALIDO)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        campagna.refresh_from_db()
        p = _partecipazione(campagna, gruppo, cfm, _capo(0), stato=StatoPartecipazione.APPROVATA)
        ContributoPartecipazione.objects.create(
            partecipazione=p, importo=Decimal("999.00"), is_simulazione=True
        )

        chiudi_campagna(FakeRequest(), utente=segreteria, campagna=campagna)

        campagna.refresh_from_db()
        assert campagna.stato == StatoCampagna.CHIUSA
        assert campagna.chiusa_il is not None
        assert not ContributoPartecipazione.objects.filter(is_simulazione=True).exists()
        definitivo = ContributoPartecipazione.objects.get(partecipazione=p, is_simulazione=False)
        assert definitivo.importo == Decimal("50.00")  # tetto: min(1000/1, 50, 51.50)

    def test_preclusa_in_impersonificazione(self, segreteria, campagna, gruppo, cfm):
        Gruppo.objects.filter(pk=gruppo.pk).update(iban=IBAN_VALIDO)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        campagna.refresh_from_db()
        _partecipazione(campagna, gruppo, cfm, _capo(0), stato=StatoPartecipazione.APPROVATA)

        request = FakeRequest(session={"hijack_history": ["1"]})
        with pytest.raises(PermissionDenied):
            chiudi_campagna(request, utente=segreteria, campagna=campagna)

        campagna.refresh_from_db()
        assert campagna.stato == StatoCampagna.IN_VALUTAZIONE

    def test_traccia_chiusura_in_auditlog(self, segreteria, campagna, gruppo, cfm):
        Gruppo.objects.filter(pk=gruppo.pk).update(iban=IBAN_VALIDO)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
        campagna.refresh_from_db()
        _partecipazione(campagna, gruppo, cfm, _capo(0), stato=StatoPartecipazione.APPROVATA)

        chiudi_campagna(FakeRequest(), utente=segreteria, campagna=campagna)

        ct = ContentType.objects.get_for_model(Campagna)
        log = LogEntry.objects.filter(content_type=ct, object_id=str(campagna.pk)).latest(
            "timestamp"
        )
        assert log.changes["stato"] == [StatoCampagna.IN_VALUTAZIONE, StatoCampagna.CHIUSA]
