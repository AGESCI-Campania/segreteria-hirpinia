"""Test delle viste di valutazione/simulazione/chiusura (D-12, D-16):
perimetro e percorso positivo, stesso schema di test_views_partecipazioni.py."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile

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
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


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
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
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
def campagna_in_valutazione(campagna_aperta) -> Campagna:
    Campagna.objects.filter(pk=campagna_aperta.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
    campagna_aperta.refresh_from_db()
    return campagna_aperta


def _partecipazione(campagna, gruppo, tipologia, codice_socio, **override) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
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


class TestCampagnaAvviaValutazioneView:
    def test_cg_non_autorizzato(self, client, campagna_aperta, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.post(f"/contributi/campagne/{campagna_aperta.pk}/avvia-valutazione/")
        assert response.status_code == 403

    def test_segreteria_avvia_valutazione(self, client, campagna_aperta, segreteria):
        client.force_login(segreteria)
        response = client.post(f"/contributi/campagne/{campagna_aperta.pk}/avvia-valutazione/")
        assert response.status_code == 302
        campagna_aperta.refresh_from_db()
        assert campagna_aperta.stato == StatoCampagna.IN_VALUTAZIONE


class TestCampagnaSimulaEChiudiView:
    def test_simula_scrive_contributi(
        self, client, campagna_in_valutazione, gruppo, cfm, segreteria
    ):
        _partecipazione(
            campagna_in_valutazione,
            gruppo,
            cfm,
            "10001",
            stato=StatoPartecipazione.APPROVATA,
        )
        client.force_login(segreteria)
        response = client.post(f"/contributi/campagne/{campagna_in_valutazione.pk}/simula/")
        assert response.status_code == 302
        assert ContributoPartecipazione.objects.filter(is_simulazione=True).exists()

    def test_chiudi_congela_e_cambia_stato(
        self, client, campagna_in_valutazione, gruppo, cfm, segreteria
    ):
        _partecipazione(
            campagna_in_valutazione,
            gruppo,
            cfm,
            "10001",
            stato=StatoPartecipazione.APPROVATA,
        )
        client.force_login(segreteria)
        response = client.post(f"/contributi/campagne/{campagna_in_valutazione.pk}/chiudi/")
        assert response.status_code == 302
        campagna_in_valutazione.refresh_from_db()
        assert campagna_in_valutazione.stato == StatoCampagna.CHIUSA
        assert ContributoPartecipazione.objects.filter(is_simulazione=False).exists()


class TestPartecipazioneValutazioneView:
    def test_cg_non_puo_approvare(self, client, campagna_in_valutazione, gruppo, cfm, cg_gruppo):
        p = _partecipazione(campagna_in_valutazione, gruppo, cfm, "10001")
        client.force_login(cg_gruppo)
        response = client.post(
            f"/contributi/campagne/{campagna_in_valutazione.pk}/partecipazioni/{p.pk}/approva/"
        )
        assert response.status_code == 403

    def test_mcz_approva(self, client, campagna_in_valutazione, gruppo, cfm, mcz):
        p = _partecipazione(campagna_in_valutazione, gruppo, cfm, "10001")
        client.force_login(mcz)
        response = client.post(
            f"/contributi/campagne/{campagna_in_valutazione.pk}/partecipazioni/{p.pk}/approva/"
        )
        assert response.status_code == 302
        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.APPROVATA

    def test_mcz_respinge_con_causale(self, client, campagna_in_valutazione, gruppo, cfm, mcz):
        p = _partecipazione(campagna_in_valutazione, gruppo, cfm, "10001")
        client.force_login(mcz)
        response = client.post(
            f"/contributi/campagne/{campagna_in_valutazione.pk}/partecipazioni/{p.pk}/respingi/",
            {"motivazione": "Documentazione insufficiente."},
        )
        assert response.status_code == 302
        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.RESPINTA

    def test_mcz_respinge_senza_causale_riresta_sul_form(
        self, client, campagna_in_valutazione, gruppo, cfm, mcz
    ):
        p = _partecipazione(campagna_in_valutazione, gruppo, cfm, "10001")
        client.force_login(mcz)
        response = client.post(
            f"/contributi/campagne/{campagna_in_valutazione.pk}/partecipazioni/{p.pk}/respingi/",
            {"motivazione": ""},
        )
        assert response.status_code == 200
        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.INSERITA

    def test_richiedi_documenti_e_carica_allegato(
        self, client, campagna_in_valutazione, gruppo, cfm, mcz, cg_gruppo
    ):
        p = _partecipazione(campagna_in_valutazione, gruppo, cfm, "10001")
        client.force_login(mcz)
        response = client.post(
            f"/contributi/campagne/{campagna_in_valutazione.pk}"
            f"/partecipazioni/{p.pk}/richiedi-documenti/"
        )
        assert response.status_code == 302
        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.DOCUMENTI_RICHIESTI

        client.force_login(cg_gruppo)
        file = SimpleUploadedFile("prova.pdf", b"contenuto", content_type="application/pdf")
        response = client.post(
            f"/contributi/campagne/{campagna_in_valutazione.pk}"
            f"/partecipazioni/{p.pk}/allegato/carica/",
            {"file": file, "tipo": "Attestato"},
        )
        assert response.status_code == 302
