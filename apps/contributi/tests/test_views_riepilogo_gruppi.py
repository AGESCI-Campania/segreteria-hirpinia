"""Test della vista CampagnaRiepilogoGruppiView (issue #11): perimetro di
accesso (RUOLI_GESTIONE_PARTECIPAZIONI), visibilità di tutti i gruppi anche
per il CG, e azione di dichiarazione "nessun rimborso"."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.contributi.models import Campagna, DichiarazioneNessunRimborso
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0199", nome="ALTRO GRUPPO")


@pytest.fixture
def campagna_aperta(gruppo, altro_gruppo) -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@x.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return utente


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@x.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


class TestCampagnaRiepilogoGruppiView:
    def test_ruolo_non_ammesso_403(self, client, campagna_aperta):
        estraneo = _persona("estraneo@x.it")
        client.force_login(estraneo)
        response = client.get(f"/contributi/campagne/{campagna_aperta.pk}/gruppi/")
        assert response.status_code == 403

    def test_cg_vede_tutti_i_gruppi(self, client, campagna_aperta, cg_gruppo, altro_gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/contributi/campagne/{campagna_aperta.pk}/gruppi/")
        assert response.status_code == 200
        codici = {r.gruppo_codice for r in response.context["righe"]}
        assert altro_gruppo.codice in codici

    def test_cg_puo_dichiarare_solo_sul_proprio_gruppo(
        self, client, campagna_aperta, cg_gruppo, gruppo, altro_gruppo
    ):
        client.force_login(cg_gruppo)
        response = client.post(
            f"/contributi/campagne/{campagna_aperta.pk}/gruppi/",
            {"gruppo": gruppo.codice, "azione": "dichiara"},
        )
        assert response.status_code == 302
        assert DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=gruppo
        ).exists()

        response = client.post(
            f"/contributi/campagne/{campagna_aperta.pk}/gruppi/",
            {"gruppo": altro_gruppo.codice, "azione": "dichiara"},
        )
        assert response.status_code == 302
        assert not DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=altro_gruppo
        ).exists()

    def test_segreteria_dichiara_e_revoca(self, client, campagna_aperta, segreteria, gruppo):
        client.force_login(segreteria)
        client.post(
            f"/contributi/campagne/{campagna_aperta.pk}/gruppi/",
            {"gruppo": gruppo.codice, "azione": "dichiara"},
        )
        assert DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=gruppo
        ).exists()

        client.post(
            f"/contributi/campagne/{campagna_aperta.pk}/gruppi/",
            {"gruppo": gruppo.codice, "azione": "revoca"},
        )
        assert not DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=gruppo
        ).exists()
