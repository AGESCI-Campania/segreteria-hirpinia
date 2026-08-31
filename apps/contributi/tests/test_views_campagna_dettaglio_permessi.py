"""Issue GitHub #2: i pulsanti di azione sulla pagina campagna devono
comparire solo per chi ha il ruolo per eseguirli — il controllo di accesso
reale resta nel service layer (D-27), qui si verifica solo la visibilità."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.contributi.campagne import puo_gestire_campagna
from apps.contributi.models import (
    Campagna,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.contributi.valutazione import puo_valutare_partecipazioni
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
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


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


@pytest.fixture
def mcz() -> Utente:
    utente = _persona("mcz@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.MCZ)
    return _con_mfa_configurata(utente)


@pytest.fixture
def campagna_aperta() -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


@pytest.fixture
def campagna_in_valutazione(campagna_aperta, gruppo, capo) -> Campagna:
    tipologia = TipologiaCampo.objects.get(codice="CFM")
    Partecipazione.objects.create(
        campagna=campagna_aperta,
        capo=capo,
        gruppo=gruppo,
        tipologia=tipologia,
        data_inizio=datetime.date(2026, 6, 1),
        data_fine=datetime.date(2026, 6, 8),
        quota_versata=Decimal("10.00"),
        stato=StatoPartecipazione.INSERITA,
    )
    Campagna.objects.filter(pk=campagna_aperta.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
    campagna_aperta.refresh_from_db()
    return campagna_aperta


class TestPulsantiGestioneCampagna:
    def test_cg_non_vede_avvia_valutazione(self, client, campagna_aperta, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_aperta.pk}/")
        assert response.status_code == 200
        assert not response.context["puo_gestire_campagna"]
        content = response.content.decode()
        assert "Avvia valutazione" not in content

    def test_segreteria_vede_avvia_valutazione(self, client, campagna_aperta, segreteria):
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna_aperta.pk}/")
        assert response.status_code == 200
        assert response.context["puo_gestire_campagna"]
        content = response.content.decode()
        assert "Avvia valutazione" in content

    def test_cg_non_vede_simula_e_chiudi(self, client, campagna_in_valutazione, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_in_valutazione.pk}/")
        content = response.content.decode()
        assert "Simula calcolo" not in content
        assert "Chiudi campagna" not in content

    def test_cg_forza_url_riceve_comunque_403(self, client, campagna_aperta, cg_gruppo):
        # Il pulsante è nascosto, ma il controllo reale resta nel service
        # layer (D-27): l'URL diretto deve restare vietato.
        client.force_login(cg_gruppo)
        response = client.post(f"/contributi/campagne/{campagna_aperta.pk}/avvia-valutazione/")
        assert response.status_code == 403


class TestPulsantiValutazionePartecipazioni:
    def test_cg_non_vede_approva_respingi(self, client, campagna_in_valutazione, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_in_valutazione.pk}/")
        assert response.status_code == 200
        assert not response.context["puo_valutare_partecipazioni"]
        content = response.content.decode()
        assert "Approva</button>" not in content
        assert ">Respingi<" not in content
        assert "Richiedi documenti" not in content

    def test_segreteria_vede_approva_respingi(self, client, campagna_in_valutazione, segreteria):
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna_in_valutazione.pk}/")
        assert response.status_code == 200
        assert response.context["puo_valutare_partecipazioni"]
        content = response.content.decode()
        assert "Approva</button>" in content
        assert ">Respingi<" in content
        assert "Richiedi documenti" in content


class TestFunzioniBool:
    def test_puo_gestire_campagna(self, cg_gruppo, segreteria, mcz):
        assert puo_gestire_campagna(cg_gruppo) is False
        assert puo_gestire_campagna(segreteria) is True
        assert puo_gestire_campagna(mcz) is False

    def test_puo_valutare_partecipazioni(self, cg_gruppo, segreteria, mcz):
        assert puo_valutare_partecipazioni(cg_gruppo) is False
        assert puo_valutare_partecipazioni(segreteria) is True
        assert puo_valutare_partecipazioni(mcz) is True
