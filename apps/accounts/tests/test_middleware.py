"""StatoUtenteMiddleware (D-06/D-24): blocca l'accesso ai moduli per utenti
IN_ATTESA/SOSPESO e per account di gruppo il cui gruppo non è più attivo,
senza impedire l'autenticazione (mostrano solo una pagina di cortesia)."""

import pytest

from apps.accounts.models import StatoUtente, TipoUtente, Utente
from apps.organizzazione.gruppi import disattiva_gruppo
from apps.organizzazione.models import Gruppo, anno_scout_corrente

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    from apps.accounts.models import Ruolo

    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


def _account_gruppo(gruppo: Gruppo) -> Utente:
    return Utente.objects.create(
        username="gruppo_e0133",
        email="e0133@campania.agesci.it",
        tipo=TipoUtente.GRUPPO,
        gruppo=gruppo,
        stato=StatoUtente.ATTIVO,
    )


class TestGruppoNonAttivo:
    def test_account_gruppo_attivo_non_bloccato(self, client, gruppo):
        utente = _account_gruppo(gruppo)
        client.force_login(utente)
        response = client.get("/")
        assert response.status_code != 302 or "gruppo-non-attivo" not in response["Location"]

    def test_account_gruppo_disattivato_reindirizzato(self, client, segreteria, gruppo):
        utente = _account_gruppo(gruppo)
        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")
        assert not gruppo.e_attivo(anno_scout_corrente())

        client.force_login(utente)
        response = client.get("/")
        assert response.status_code == 302
        assert response["Location"] == "/accounts/gruppo-non-attivo/"

    def test_pagina_di_cortesia_accessibile(self, client, segreteria, gruppo):
        utente = _account_gruppo(gruppo)
        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")
        client.force_login(utente)
        response = client.get("/accounts/gruppo-non-attivo/")
        assert response.status_code == 200

    def test_persona_non_toccata_dal_controllo(self, client):
        persona = _persona("persona@campania.agesci.it")
        client.force_login(persona)
        response = client.get("/")
        assert response.status_code == 200
