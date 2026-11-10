"""Breadcrumb automatico derivato dal menu (apps.core.context_processors.breadcrumb)."""

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.core.context_processors import breadcrumb

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


def test_anonimo_nessun_breadcrumb():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    assert breadcrumb(request) == {}


def test_home_solo_home(client, segreteria):
    client.force_login(segreteria)
    response = client.get("/")
    assert response.context["breadcrumb_items"] == [{"label": "Home", "url": "/"}]


def test_pagina_di_menu_ha_sezione_e_voce(client, segreteria):
    client.force_login(segreteria)
    response = client.get("/gruppi/")
    items = response.context["breadcrumb_items"]
    assert items[0] == {"label": "Home", "url": "/"}
    assert items[1] == {"label": "Anagrafica"}
    assert items[2] == {"label": "Gruppi"}


def test_pagina_non_di_menu_ha_solo_home(client, segreteria):
    client.force_login(segreteria)
    response = client.get("/gruppi/nuovo/")
    assert response.context["breadcrumb_items"] == [{"label": "Home", "url": "/"}]


def test_landing_di_modulo_ha_sezione_e_voce(client, segreteria):
    """La landing page di un modulo con sottovoci (Nota Spese) è l'URL della
    voce stessa: nessun terzo livello, il breadcrumb resta a 2 livelli come
    una voce semplice."""
    client.force_login(segreteria)
    response = client.get("/note-spese/")
    items = response.context["breadcrumb_items"]
    assert items[0] == {"label": "Home", "url": "/"}
    assert items[1] == {"label": "Moduli"}
    assert items[2] == {"label": "Nota Spese"}


def test_sottovoce_di_modulo_ha_sezione_voce_e_sottovoce(client, segreteria):
    client.force_login(segreteria)
    response = client.get("/note-spese/elenco/")
    items = response.context["breadcrumb_items"]
    assert items[0] == {"label": "Home", "url": "/"}
    assert items[1] == {"label": "Moduli"}
    assert items[2] == {"label": "Nota Spese", "url": "/note-spese/"}
    assert items[3] == {"label": "Note spese"}


class TestMarkupBreadcrumb:
    """Il breadcrumb è il partial nativo del tema (agesci_theme/partials/
    breadcrumb.html, incluso nella barra inferiore dell'header di
    agesci_theme/base.html), senza override locale, pilotato dalla variabile
    di contesto `breadcrumb_items`."""

    def test_breadcrumb_nativo_presente(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/")
        assert 'class="breadcrumb' in response.content.decode()

    def test_pagina_figlia_ha_comunque_il_breadcrumb(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/gruppi/nuovo/")
        assert 'class="breadcrumb' in response.content.decode()


class TestSidebarFisarmonica:
    """Sidebar a fisarmonica: le sezioni partono chiuse, si apre quella della
    pagina corrente (anche per una pagina sotto una voce) e il sottogruppo del
    modulo che la contiene; aprirne una chiude le altre (data-bs-parent)."""

    def test_sottovoce_apre_sezione_e_modulo(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/note-spese/elenco/")
        assert response.context["sezione_menu_aperta"] == "Moduli"
        assert response.context["voce_menu_aperta"] == "/note-spese/"
        html = response.content.decode()
        assert html.count('class="collapse list-unstyled ps-7 show"') == 2
        assert 'href="/note-spese/elenco/" class="ag-sidebar__nav-link active"' in html

    def test_impostazioni_nota_spese_aprono_amministrazione(self, client):
        # La voce "Impostazioni Nota spese" è solo di ADMIN/RdZ: per loro
        # /note-spese/impostazioni/ vince su /note-spese/ (Moduli).
        admin = _persona("admin@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        client.force_login(_con_mfa_configurata(admin))
        response = client.get("/note-spese/impostazioni/")
        assert response.context["sezione_menu_aperta"] == "Amministrazione"
        assert response.context["voce_menu_aperta"] == "/note-spese/impostazioni/"

    def test_home_tutte_chiuse(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/")
        assert response.context["sezione_menu_aperta"] is None
        html = response.content.decode()
        assert 'list-unstyled ps-7 show"' not in html
        assert 'data-bs-parent="#agSidebar"' in html
