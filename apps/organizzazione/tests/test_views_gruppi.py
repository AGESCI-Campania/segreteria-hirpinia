"""Test delle viste del ciclo di vita del gruppo (D-24): perimetro e
percorso positivo, stesso schema di apps/contributi/tests/test_views_*.py."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import Gruppo, StatoGruppoAnno, anno_scout_corrente

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
        response = client.get("/gruppi/")
        assert response.status_code == 403

    def test_segreteria_accede_alla_lista(self, client, segreteria, gruppo):
        client.force_login(segreteria)
        response = client.get("/gruppi/")
        assert response.status_code == 200


class TestGruppoCreaView:
    def test_crea_gruppo(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post(
            "/gruppi/nuovo/",
            {"codice": "E0199", "nome": "NUOVO GRUPPO", "email_istituzionale": "n@x.it"},
        )
        assert response.status_code == 302
        assert Gruppo.objects.filter(codice="E0199").exists()


class TestGruppoDisattivaView:
    def test_get_mostra_conteggi(self, client, segreteria, gruppo):
        client.force_login(segreteria)
        response = client.get(f"/gruppi/{gruppo.codice}/disattiva/")
        assert response.status_code == 200
        assert "conteggi" in response.context

    def test_post_disattiva(self, client, segreteria, gruppo):
        client.force_login(segreteria)
        response = client.post(f"/gruppi/{gruppo.codice}/disattiva/", {"motivo": "Sciolto"})
        assert response.status_code == 302
        assert not gruppo.e_attivo(anno_scout_corrente())


class TestGruppoRiattivaView:
    def test_post_riattiva(self, client, segreteria, gruppo):
        anno = anno_scout_corrente()
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=anno, attivo=False)
        client.force_login(segreteria)
        response = client.post(
            f"/gruppi/{gruppo.codice}/riattiva/",
            {"anno_scout": anno + 1, "motivo": "Riattivo"},
        )
        assert response.status_code == 302
        assert gruppo.e_attivo(anno + 1)


class TestGruppoGestioneView:
    def _dati(self):
        return {
            "email_alternativa": "alt@example.com",
            "indirizzo": "Via Roma",
            "civico": "1",
            "cap": "83100",
            "comune": "Avellino",
            "provincia": "AV",
            "codice_fiscale": "12345678901",
        }

    def test_cg_accede_e_modifica_il_proprio_gruppo(self, client, cg_gruppo, gruppo):
        client.force_login(cg_gruppo)
        response = client.get(f"/gruppi/{gruppo.codice}/gestione/")
        assert response.status_code == 200

        response = client.post(f"/gruppi/{gruppo.codice}/gestione/", self._dati())
        assert response.status_code == 302
        gruppo.refresh_from_db()
        assert gruppo.email_alternativa == "alt@example.com"

    def test_cg_non_accede_a_un_altro_gruppo(self, client, cg_gruppo):
        altro = Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")
        client.force_login(cg_gruppo)
        response = client.get(f"/gruppi/{altro.codice}/gestione/")
        assert response.status_code == 403

    def test_segreteria_accede_a_e9001(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/gruppi/E9001/gestione/")
        assert response.status_code == 200

    def test_email_istituzionale_forzata_nel_post_non_viene_scritta(
        self, client, segreteria, gruppo
    ):
        client.force_login(segreteria)
        dati = self._dati()
        dati["email_istituzionale"] = "forzata@x.it"
        client.post(f"/gruppi/{gruppo.codice}/gestione/", dati)
        gruppo.refresh_from_db()
        assert gruppo.email_istituzionale == ""

    def test_link_visibile_in_lista_gruppi(self, client, segreteria, gruppo):
        client.force_login(segreteria)
        response = client.get("/gruppi/")
        assert f"/gruppi/{gruppo.codice}/gestione/" in response.content.decode()

    def test_breadcrumb_pagina_figlia(self, client, segreteria, gruppo):
        # Segreteria arriva a gruppo_gestione via il link nella lista "Gruppi"
        # (voce di menu diversa dalla pagina corrente): a differenza del CG,
        # per cui "Il mio gruppo" punta esattamente a questa stessa URL e fa
        # scattare il ramo standard sezione/voce, qui si esercita
        # BreadcrumbExtraMixin.
        client.force_login(segreteria)
        response = client.get(f"/gruppi/{gruppo.codice}/gestione/")
        items = response.context["breadcrumb_items"]
        assert items[0] == {"label": "Home", "url": "/"}
        assert items[-3] == {"label": "Gruppi"}
        assert items[-2] == {"label": gruppo.nome}
        assert items[-1] == {"label": "Gestione"}

    def test_breadcrumb_cg_su_il_mio_gruppo_usa_la_voce_di_menu(self, client, cg_gruppo, gruppo):
        # "Il mio gruppo" punta esattamente alla stessa URL: il ramo standard
        # sezione/voce del breadcrumb la intercetta prima di arrivare al
        # mixin, comportamento coerente con tutte le altre voci di menu.
        client.force_login(cg_gruppo)
        response = client.get(f"/gruppi/{gruppo.codice}/gestione/")
        items = response.context["breadcrumb_items"]
        assert items == [
            {"label": "Home", "url": "/"},
            {"label": "Anagrafica"},
            {"label": "Il mio gruppo"},
        ]
