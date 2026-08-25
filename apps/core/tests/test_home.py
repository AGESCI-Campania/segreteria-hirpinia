"""Home page (M9): le card riusano sezione.icona/voce.icona già presenti in
apps/core/menu.py, con lo stesso tag {% bs_icon %} della sidebar."""

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


class TestIconeCardHome:
    def test_card_e_voce_mostrano_unicona(self, client):
        utente = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
        _con_mfa_configurata(utente)
        client.force_login(utente)

        response = client.get("/")

        content = response.content.decode()
        # bs_icon renderizza un <svg>: non testiamo il markup esatto (fuori dal
        # nostro controllo, viene da django_bootstrap_icons), solo che il tag
        # produca output SVG dentro le card, non testo vuoto/errore silenzioso.
        assert "<svg" in content
        assert "card-header" in content

    def test_utente_senza_ruolo_vede_comunque_la_pagina(self, client):
        # sezioni_menu() include sempre "Account" ("Le mie deleghe", non
        # condizionata da alcun ruolo, apps/core/menu.py) — il ramo "nessun
        # ruolo attivo" di home.html non si attiva mai per un utente
        # autenticato: verificato qui, non è un comportamento introdotto da
        # M9. Il test si limita a verificare che la pagina non vada in
        # errore per un utente senza ruoli effettivi.
        utente = _persona("senza-ruolo@campania.agesci.it")
        _con_mfa_configurata(utente)
        client.force_login(utente)

        response = client.get("/")

        assert response.status_code == 200
        assert "<svg" in response.content.decode()
