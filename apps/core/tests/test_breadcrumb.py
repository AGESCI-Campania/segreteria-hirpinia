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
    """Migrazione a django-agesci-campania-coreui-theme: il breadcrumb non è
    più un partial separato con override locale (icona Home rimossa insieme
    all'override), ma markup nativo inline in agesci_coreui/base.html,
    pilotato dalla stessa variabile di contesto `breadcrumb_items`."""

    def test_breadcrumb_nativo_presente(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/")
        assert 'class="breadcrumb' in response.content.decode()

    def test_pagina_figlia_ha_comunque_il_breadcrumb(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/gruppi/nuovo/")
        assert 'class="breadcrumb' in response.content.decode()
