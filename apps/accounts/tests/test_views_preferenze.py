"""Preferenze personali (issue #7): disponibili a qualunque utente loggato,
senza gate di ruolo — a differenza del default di sistema in Impostazioni."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


def test_anonimo_non_accede(client):
    response = client.get("/accounts/preferenze/")
    assert response.status_code == 302


def test_cg_senza_ruoli_privilegiati_accede_e_salva(client):
    utente = _con_mfa_configurata(_persona("cg@campania.agesci.it"))
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    client.force_login(utente)

    assert client.get("/accounts/preferenze/").status_code == 200

    response = client.post("/accounts/preferenze/", {"branca_tema_preferita": "rs"})
    assert response.status_code == 302
    utente.refresh_from_db()
    assert utente.branca_tema_preferita == "rs"


def test_preferenza_di_un_utente_non_tocca_un_altro(client):
    utente_a = _con_mfa_configurata(_persona("a@campania.agesci.it"))
    utente_b = _con_mfa_configurata(_persona("b@campania.agesci.it"))

    client.force_login(utente_a)
    client.post("/accounts/preferenze/", {"branca_tema_preferita": "eg"})

    utente_a.refresh_from_db()
    utente_b.refresh_from_db()
    assert utente_a.branca_tema_preferita == "eg"
    assert utente_b.branca_tema_preferita == ""
