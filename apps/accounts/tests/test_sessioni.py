"""Sessione utente (issue #9), sopra `allauth.usersessions.models.UserSession`
(vedi `apps/accounts/sessioni.py`): proprie sessioni per qualunque utente
loggato, tutte le sessioni riservate ad Admin/Segreteria diretti (RDZ
escluso di proposito)."""

from importlib import import_module

import pytest
from allauth.mfa.models import Authenticator
from allauth.usersessions.models import UserSession
from django.conf import settings
from django.contrib.auth import login as django_login
from django.test import RequestFactory

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    utente = Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


def _sessione_reale(utente: Utente, *, user_agent: str) -> UserSession:
    """UserSession collegata a una vera riga django_session (login completo,
    non solo `_auth_user_id`: senza `_auth_user_hash` Django la considera
    invalida): senza questo, `purge()` (chiamato da `sessioni_di`/
    `tutte_le_sessioni`) la scarterebbe subito, come farebbe correttamente
    anche in produzione con una sessione non più valida."""
    engine = import_module(settings.SESSION_ENGINE)
    store = engine.SessionStore()
    store.create()
    request = RequestFactory().get("/")
    request.session = store
    django_login(request, utente, backend="django.contrib.auth.backends.ModelBackend")
    store.save()
    return UserSession.objects.create(
        user=utente, session_key=store.session_key, ip="127.0.0.1", user_agent=user_agent
    )


class TestSessioniListaView:
    def test_mostra_solo_le_proprie(self, client):
        utente = _persona("cg@campania.agesci.it")
        altro = _persona("altro@campania.agesci.it")
        client.force_login(utente)
        _sessione_reale(utente, user_agent="pytest-agent")
        _sessione_reale(altro, user_agent="altro-agent")

        response = client.get("/accounts/sessioni/")

        assert response.status_code == 200
        assert b"pytest-agent" in response.content
        assert b"altro-agent" not in response.content

    def test_anonimo_non_accede(self, client):
        assert client.get("/accounts/sessioni/").status_code == 302


class TestSessioneTerminaView:
    def test_non_puo_terminare_una_sessione_altrui(self, client):
        utente = _persona("cg2@campania.agesci.it")
        altro = _persona("altro2@campania.agesci.it")
        client.force_login(utente)
        sessione_altrui = UserSession.objects.create(
            user=altro, session_key="altra-sessione-2", ip="10.0.0.1", user_agent="altro"
        )

        response = client.post(f"/accounts/sessioni/{sessione_altrui.pk}/termina/")

        assert response.status_code == 302
        assert UserSession.objects.filter(pk=sessione_altrui.pk).exists()

    def test_termina_una_propria(self, client):
        utente = _persona("cg5@campania.agesci.it")
        client.force_login(utente)
        sessione = UserSession.objects.create(
            user=utente, session_key="sess-propria", ip="127.0.0.1", user_agent="mio-browser"
        )

        response = client.post(f"/accounts/sessioni/{sessione.pk}/termina/")

        assert response.status_code == 302
        assert not UserSession.objects.filter(pk=sessione.pk).exists()


class TestSessioniTutteListaView:
    def test_richiede_admin_o_segreteria(self, client):
        cg = _persona("cg3@campania.agesci.it")
        client.force_login(cg)
        assert client.get("/accounts/sessioni/tutte/").status_code == 403

    def test_rdz_escluso(self, client):
        rdz = _persona("rdz@campania.agesci.it")
        Ruolo.objects.create(utente=rdz, tipo=Ruolo.Tipo.RDZ)
        client.force_login(rdz)
        assert client.get("/accounts/sessioni/tutte/").status_code == 403

    def test_admin_vede_le_sessioni_di_tutti(self, client):
        cg = _persona("cg3b@campania.agesci.it")
        admin = _persona("admin@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        client.force_login(admin)
        _sessione_reale(cg, user_agent="cg-agent")

        response = client.get("/accounts/sessioni/tutte/")

        assert response.status_code == 200
        assert b"cg-agent" in response.content

    def test_segreteria_vede_le_sessioni_di_tutti(self, client):
        cg = _persona("cg3c@campania.agesci.it")
        segreteria = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        client.force_login(segreteria)
        _sessione_reale(cg, user_agent="cg-agent-segreteria")

        response = client.get("/accounts/sessioni/tutte/")

        assert response.status_code == 200
        assert b"cg-agent-segreteria" in response.content


class TestSessioneTerminaAltruiView:
    def test_admin_termina_sessione_di_un_altro_utente(self, client):
        admin = _persona("admin2@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        cg = _persona("cg4@campania.agesci.it")
        sessione = UserSession.objects.create(
            user=cg, session_key="sess-cg-4", ip="127.0.0.1", user_agent="cg-agent-4"
        )
        client.force_login(admin)

        response = client.post(f"/accounts/sessioni/tutte/{sessione.pk}/termina/")

        assert response.status_code == 302
        assert not UserSession.objects.filter(pk=sessione.pk).exists()

    def test_cg_non_puo_terminare_sessioni_altrui(self, client):
        cg = _persona("cg6@campania.agesci.it")
        altro = _persona("altro6@campania.agesci.it")
        sessione = UserSession.objects.create(
            user=altro, session_key="sess-altro-6", ip="127.0.0.1", user_agent="altro-6"
        )
        client.force_login(cg)

        response = client.post(f"/accounts/sessioni/tutte/{sessione.pk}/termina/")

        assert response.status_code == 403
        assert UserSession.objects.filter(pk=sessione.pk).exists()
