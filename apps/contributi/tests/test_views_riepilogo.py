"""Test delle viste di riepilogo/report PDF (D-13): sezioni nel dettaglio
campagna e generazione del PDF, stesso schema di test_views_*.py."""

import datetime
from decimal import Decimal

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
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1", iban=IBAN_VALIDO)


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0199", nome="ALTRO GRUPPO")


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return _con_mfa_configurata(utente)


@pytest.fixture
def campagna_chiusa(gruppo, altro_gruppo, cfm) -> Campagna:
    c = Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )
    Campagna.objects.filter(pk=c.pk).update(stato=StatoCampagna.CHIUSA)
    c.refresh_from_db()

    for codice_socio, g, importo in (("10001", gruppo, "50.00"), ("10002", altro_gruppo, "30.00")):
        capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
        p = Partecipazione(
            campagna=c,
            capo=capo,
            gruppo=g,
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
            partecipazione=p, importo=Decimal(importo), is_simulazione=False
        )
    return c


class TestCampagnaDettaglioRiepilogo:
    def test_cg_vede_totali_altri_gruppi_senza_iban(self, client, campagna_chiusa, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_chiusa.pk}/")
        assert response.status_code == 200
        assert "E0199" in response.content.decode()
        assert IBAN_VALIDO not in response.content.decode()

    def test_staff_non_vede_tabella_altri_gruppi_vuota(self, client, campagna_chiusa, segreteria):
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna_chiusa.pk}/")
        assert response.status_code == 200
        assert response.context["totali_altri_gruppi"] == []


class TestCampagnaReportPdfView:
    def test_cg_non_autorizzato(self, client, campagna_chiusa, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_chiusa.pk}/riepilogo.pdf")
        assert response.status_code == 403

    def test_segreteria_scarica_pdf(self, client, campagna_chiusa, segreteria):
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna_chiusa.pk}/riepilogo.pdf")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content[:4] == b"%PDF"
        assert IBAN_VALIDO.encode() not in response.content
