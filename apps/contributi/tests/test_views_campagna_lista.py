"""Issue #14 (pulsanti Impostazioni/Nuova campagna nascosti senza permesso,
stesso schema di #2) e #15 (jumbotron ultima campagna) su `CampagnaListaView`."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.contributi.models import Campagna
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

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
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return _con_mfa_configurata(utente)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


def _campagna(anno: int) -> Campagna:
    return Campagna.objects.create(
        anno=anno,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(anno - 1, 10, 1),
        data_fine_inserimento=datetime.date(anno, 9, 30),
    )


class TestPulsantiCampagnaLista:
    def test_cg_non_vede_impostazioni_ne_nuova_campagna(self, client, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get("/contributi/campagne/")
        assert response.status_code == 200
        assert not response.context["puo_gestire_campagna"]
        assert not response.context["puo_gestire_impostazioni"]
        content = response.content.decode()
        assert "Nuova campagna" not in content
        assert 'href="/impostazioni/"' not in content

    def test_segreteria_vede_impostazioni_e_nuova_campagna(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/contributi/campagne/")
        assert response.status_code == 200
        assert response.context["puo_gestire_campagna"]
        assert response.context["puo_gestire_impostazioni"]
        content = response.content.decode()
        assert "Nuova campagna" in content
        assert "Impostazioni" in content


class TestJumbotronUltimaCampagna:
    def test_ultima_campagna_e_la_piu_recente(self, client, segreteria):
        _campagna(2025)
        recente = _campagna(2026)
        client.force_login(segreteria)
        response = client.get("/contributi/campagne/")
        assert response.context["ultima_campagna"] == recente

    def test_ultima_campagna_resta_anche_in_tabella(self, client, segreteria):
        recente = _campagna(2026)
        client.force_login(segreteria)
        response = client.get("/contributi/campagne/")
        assert recente in response.context["campagne"]

    def test_nessuna_campagna_ultima_campagna_none(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/contributi/campagne/")
        assert response.context["ultima_campagna"] is None
