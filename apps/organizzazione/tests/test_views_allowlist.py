"""Test delle viste dell'allowlist gruppi: stesso schema di
test_views_gruppi.py (perimetro ruoli + percorso positivo)."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import AllowlistGruppo, Gruppo

pytestmark = pytest.mark.django_db


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
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return _con_mfa_configurata(utente)


class TestPerimetro:
    def test_cg_non_accede_alla_lista(self, client, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get("/gruppi/allowlist/")
        assert response.status_code == 403

    def test_segreteria_accede_alla_lista(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/gruppi/allowlist/")
        assert response.status_code == 200


class TestAllowlistCreaView:
    def test_crea_voce(self, client, segreteria, gruppo):
        client.force_login(segreteria)
        response = client.post(
            "/gruppi/allowlist/nuova/",
            {"codice_gruppo": gruppo.codice, "email": "nuovo@campania.agesci.it"},
        )
        assert response.status_code == 302
        assert AllowlistGruppo.objects.filter(email="nuovo@campania.agesci.it").exists()

    def test_gruppo_inesistente_mostra_errore(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post(
            "/gruppi/allowlist/nuova/",
            {"codice_gruppo": "E9999", "email": "nuovo@campania.agesci.it"},
        )
        assert response.status_code == 200
        assert not AllowlistGruppo.objects.filter(email="nuovo@campania.agesci.it").exists()


class TestAllowlistEliminaView:
    def test_elimina_voce(self, client, segreteria, gruppo):
        voce = AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")
        client.force_login(segreteria)
        response = client.post(f"/gruppi/allowlist/{voce.pk}/elimina/")
        assert response.status_code == 302
        assert not AllowlistGruppo.objects.filter(pk=voce.pk).exists()
