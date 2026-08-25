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


class TestIconaHome:
    """M13: override locale di agesci_theme/partials/breadcrumb.html.
    bs_icon renderizza un <svg> (django_bootstrap_icons): verifichiamo che
    compaia dentro il breadcrumb, non il markup esatto (fuori controllo)."""

    def _svg_nel_breadcrumb(self, content: str) -> bool:
        inizio = content.index('class="breadcrumb-agesci"')
        fine = content.index("</nav>", inizio)
        return "<svg" in content[inizio:fine]

    def test_home_ha_icona(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/")
        assert self._svg_nel_breadcrumb(response.content.decode())

    def test_pagina_figlia_ha_comunque_icona_home(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/gruppi/nuovo/")
        assert self._svg_nel_breadcrumb(response.content.decode())
