"""Invito diretto ristretto ad ADMIN/SEGRETERIA, fuso dentro "Ruoli" (M10):
RDZ perde la creazione ma mantiene la sola visualizzazione dello storico."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def admin() -> Utente:
    utente = _persona("admin@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
    return _con_mfa_configurata(utente)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def rdz() -> Utente:
    utente = _persona("rdz@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
    return _con_mfa_configurata(utente)


class TestPerimetroInvitoCreaView:
    def test_admin_accede(self, client, admin):
        client.force_login(admin)
        assert client.get("/accounts/inviti/nuovo/").status_code == 200

    def test_segreteria_accede(self, client, segreteria):
        client.force_login(segreteria)
        assert client.get("/accounts/inviti/nuovo/").status_code == 200

    def test_rdz_non_accede(self, client, rdz):
        client.force_login(rdz)
        assert client.get("/accounts/inviti/nuovo/").status_code == 403

    def test_rdz_accede_comunque_allo_storico(self, client, rdz):
        client.force_login(rdz)
        assert client.get("/accounts/inviti/").status_code == 200


class TestFormRuoloProposto:
    def test_ruolo_proposto_obbligatorio(self, client, admin):
        client.force_login(admin)
        response = client.post("/accounts/inviti/nuovo/", {"email": "nuovo@campania.agesci.it"})
        assert response.status_code == 200
        assert response.context["form"].errors.get("ruolo_proposto")

    def test_solo_admin_segreteria_tra_le_scelte(self, client, admin):
        client.force_login(admin)
        response = client.get("/accounts/inviti/nuovo/")
        valori = dict(response.context["form"].fields["ruolo_proposto"].choices)
        assert set(valori) == {Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA}

    def test_crea_invito_per_segreteria(self, client, admin):
        from apps.accounts.models import InvitoAttivazione

        client.force_login(admin)
        response = client.post(
            "/accounts/inviti/nuovo/",
            {"email": "nuovo@campania.agesci.it", "ruolo_proposto": Ruolo.Tipo.SEGRETERIA},
        )
        assert response.status_code == 302
        invito = InvitoAttivazione.objects.get(email="nuovo@campania.agesci.it")
        assert invito.ruolo_proposto == Ruolo.Tipo.SEGRETERIA


class TestBreadcrumb:
    def test_breadcrumb_nuovo_invito(self, client, admin):
        client.force_login(admin)
        response = client.get("/accounts/inviti/nuovo/")
        items = response.context["breadcrumb_items"]
        assert items[-3] == {"label": "Amministrazione"}
        assert items[-2]["label"] == "Ruoli"
        assert items[-1] == {"label": "Nuovo invito"}

    def test_breadcrumb_storico_inviti(self, client, admin):
        client.force_login(admin)
        response = client.get("/accounts/inviti/")
        items = response.context["breadcrumb_items"]
        assert items[-1] == {"label": "Storico inviti"}


class TestMenu:
    def test_voce_inviti_non_compare_piu(self, admin):
        from apps.core.menu import sezioni_menu

        sezioni = sezioni_menu(admin)
        etichette = {voce.etichetta for sezione in sezioni for voce in sezione.voci}
        assert "Inviti" not in etichette


class TestPulsantiRuoloLista:
    def test_admin_vede_entrambi_i_pulsanti(self, client, admin):
        client.force_login(admin)
        content = client.get("/accounts/ruoli/").content.decode()
        assert "Nuovo invito" in content
        assert "Storico inviti" in content

    def test_rdz_vede_solo_storico(self, client, rdz):
        client.force_login(rdz)
        content = client.get("/accounts/ruoli/").content.decode()
        assert "Nuovo invito" not in content
        assert "Storico inviti" in content
