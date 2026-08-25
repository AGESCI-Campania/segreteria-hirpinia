"""Assegnazione diretta di un ruolo, senza invito, a un utente già attivo
(M11)."""

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
def estraneo() -> Utente:
    utente = _persona("estraneo@campania.agesci.it")
    return _con_mfa_configurata(utente)


@pytest.fixture
def destinatario() -> Utente:
    return _persona("dest@campania.agesci.it")


class TestPerimetro:
    def test_estraneo_non_accede_alla_ricerca(self, client, estraneo):
        client.force_login(estraneo)
        assert client.get("/accounts/ruoli/assegna/").status_code == 403

    def test_estraneo_non_accede_al_form(self, client, estraneo, destinatario):
        client.force_login(estraneo)
        response = client.get(f"/accounts/ruoli/assegna/nuovo/?utente_id={destinatario.pk}")
        assert response.status_code == 403


class TestRicerca:
    def test_senza_query_nessun_risultato(self, client, admin):
        client.force_login(admin)
        response = client.get("/accounts/ruoli/assegna/")
        assert list(response.context["risultati"]) == []

    def test_trova_per_email(self, client, admin, destinatario):
        client.force_login(admin)
        response = client.get("/accounts/ruoli/assegna/", {"q": "dest@"})
        assert destinatario in list(response.context["risultati"])


class TestAssegnazione:
    def test_get_form_mostra_utente_destinatario(self, client, admin, destinatario):
        client.force_login(admin)
        response = client.get(f"/accounts/ruoli/assegna/nuovo/?utente_id={destinatario.pk}")
        assert response.status_code == 200
        assert response.context["utente_destinatario"] == destinatario

    def test_cg_non_e_tra_le_scelte(self, client, admin, destinatario):
        client.force_login(admin)
        response = client.get(f"/accounts/ruoli/assegna/nuovo/?utente_id={destinatario.pk}")
        valori = [c[0] for c in response.context["form"].fields["tipo"].choices]
        assert Ruolo.Tipo.CG not in valori

    def test_post_crea_il_ruolo(self, client, admin, destinatario):
        client.force_login(admin)
        response = client.post(
            "/accounts/ruoli/assegna/nuovo/",
            {
                "utente_id": destinatario.pk,
                "tipo": Ruolo.Tipo.SEGRETERIA,
                "branca": "",
                "settore": "",
                "data_fine": "",
            },
        )
        assert response.status_code == 302
        assert Ruolo.objects.filter(
            utente=destinatario, tipo=Ruolo.Tipo.SEGRETERIA, attivo=True
        ).exists()

    def test_post_iabz_senza_branca_e_un_errore(self, client, admin, destinatario):
        client.force_login(admin)
        response = client.post(
            "/accounts/ruoli/assegna/nuovo/",
            {
                "utente_id": destinatario.pk,
                "tipo": Ruolo.Tipo.IABZ,
                "branca": "",
                "settore": "",
                "data_fine": "",
            },
        )
        assert response.status_code == 200
        assert not Ruolo.objects.filter(utente=destinatario, tipo=Ruolo.Tipo.IABZ).exists()

    def test_post_duplicato_mostra_errore_senza_creare(self, client, admin, destinatario):
        client.force_login(admin)
        dati = {
            "utente_id": destinatario.pk,
            "tipo": Ruolo.Tipo.SEGRETERIA,
            "branca": "",
            "settore": "",
            "data_fine": "",
        }
        client.post("/accounts/ruoli/assegna/nuovo/", dati)

        response = client.post("/accounts/ruoli/assegna/nuovo/", dati)

        assert response.status_code == 200
        assert Ruolo.objects.filter(utente=destinatario, tipo=Ruolo.Tipo.SEGRETERIA).count() == 1


class TestBreadcrumb:
    def test_breadcrumb_ricerca(self, client, admin):
        client.force_login(admin)
        response = client.get("/accounts/ruoli/assegna/")
        assert response.context["breadcrumb_items"][-1] == {"label": "Assegna ruolo"}

    def test_breadcrumb_form(self, client, admin, destinatario):
        client.force_login(admin)
        response = client.get(f"/accounts/ruoli/assegna/nuovo/?utente_id={destinatario.pk}")
        assert response.context["breadcrumb_items"][-1] == {"label": "Assegna ruolo"}


class TestPulsanteInRuoloLista:
    def test_pulsante_aggiungi_ruolo_presente(self, client, admin):
        client.force_login(admin)
        content = client.get("/accounts/ruoli/").content.decode()
        assert "Aggiungi ruolo" in content
