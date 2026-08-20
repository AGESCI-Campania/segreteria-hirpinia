"""Test delle viste di generazione bonifici e liquidazione (D-12, D-14):
perimetro e percorso positivo, stesso schema di test_views_valutazione.py."""

import csv
import datetime
import io
from decimal import Decimal

import openpyxl
import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026
IBAN_VALIDO = "IT60X0542811101000000123456"


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def cg_gruppo() -> Utente:
    gruppo = Gruppo.objects.create(codice="E0199", nome="ALTRO GRUPPO")
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return _con_mfa_configurata(utente)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1", iban=IBAN_VALIDO)


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def campagna_chiusa(gruppo, cfm) -> Campagna:
    c = Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )
    Campagna.objects.filter(pk=c.pk).update(stato=StatoCampagna.CHIUSA)
    c.refresh_from_db()

    capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    p = Partecipazione(
        campagna=c,
        capo=capo,
        gruppo=gruppo,
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
    return c


class TestBonificiGeneraView:
    def test_cg_non_autorizzato(self, client, campagna_chiusa, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_chiusa.pk}/bonifici/")
        assert response.status_code == 403

    def test_genera_csv(self, client, campagna_chiusa, segreteria):
        client.force_login(segreteria)
        response = client.post(
            f"/contributi/campagne/{campagna_chiusa.pk}/bonifici/",
            {"causale": "Contributo FoCa 2026", "formato": "csv"},
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        righe = list(csv.reader(io.StringIO(response.content.decode("utf-8")), delimiter=";"))
        assert righe[0] == [
            "codice",
            "denominazione",
            "intestazione_conto",
            "iban",
            "importo",
            "causale",
        ]
        assert righe[1][0] == "E0133"
        assert righe[1][4] == "50.00"

    def test_genera_xlsx(self, client, campagna_chiusa, segreteria):
        client.force_login(segreteria)
        response = client.post(
            f"/contributi/campagne/{campagna_chiusa.pk}/bonifici/",
            {"causale": "Contributo FoCa 2026", "formato": "xlsx"},
        )
        assert response.status_code == 200
        cartella = openpyxl.load_workbook(io.BytesIO(response.content))
        righe = list(cartella.active.iter_rows(values_only=True))
        assert righe[0] == (
            "codice",
            "denominazione",
            "intestazione_conto",
            "iban",
            "importo",
            "causale",
        )
        assert righe[1][0] == "E0133"


class TestCampagnaLiquidaView:
    def test_cg_non_autorizzato(self, client, campagna_chiusa, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.post(f"/contributi/campagne/{campagna_chiusa.pk}/liquida/")
        assert response.status_code == 403

    def test_segreteria_liquida(self, client, campagna_chiusa, segreteria):
        client.force_login(segreteria)
        response = client.post(
            f"/contributi/campagne/{campagna_chiusa.pk}/liquida/",
            {"data_liquidazione": "2026-09-25", "riferimento_bonifico": "Distinta n. 42"},
        )
        assert response.status_code == 302
        campagna_chiusa.refresh_from_db()
        assert campagna_chiusa.stato == StatoCampagna.LIQUIDATA

    def test_senza_riferimento_riresta_sul_form(self, client, campagna_chiusa, segreteria):
        client.force_login(segreteria)
        response = client.post(
            f"/contributi/campagne/{campagna_chiusa.pk}/liquida/",
            {"data_liquidazione": "2026-09-25", "riferimento_bonifico": ""},
        )
        assert response.status_code == 200
        campagna_chiusa.refresh_from_db()
        assert campagna_chiusa.stato == StatoCampagna.CHIUSA
