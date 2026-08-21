import datetime

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied
from hijack.signals import hijack_ended, hijack_started

from apps.accounts.audit import vieta_in_impersonificazione
from apps.accounts.deleghe import crea_delega
from apps.accounts.models import Ruolo, SessioneImpersonificazione, TipoUtente, Utente
from apps.accounts.permessi import puo_impersonare, puo_impersonare_qualcuno

pytestmark = pytest.mark.django_db

DOMANI = datetime.date.today() + datetime.timedelta(days=1)


def _persona(email, **kwargs):
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


class FakeSession(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeRequest:
    def __init__(self, session=None, remote_addr="127.0.0.1"):
        self.session = FakeSession(session or {})
        self.META = {"REMOTE_ADDR": remote_addr}


class TestPuoImpersonare:
    def test_admin_reale_puo_impersonare(self):
        admin = _persona("admin@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        bersaglio = _persona("cg@campania.agesci.it")
        assert puo_impersonare(hijacker=admin, hijacked=bersaglio) is True

    def test_admin_per_delega_non_puo_impersonare(self):
        """D-27: solo ADMIN, nemmeno per delega."""
        titolare = _persona("titolare@campania.agesci.it")
        ruolo_admin = Ruolo.objects.create(utente=titolare, tipo=Ruolo.Tipo.ADMIN)
        delegato = _persona("delegato@campania.agesci.it")
        crea_delega(
            delegante=titolare,
            ruolo=ruolo_admin,
            email_delegato=delegato.email,
            data_fine=DOMANI,
        )
        bersaglio = _persona("cg@campania.agesci.it")
        assert puo_impersonare(hijacker=delegato, hijacked=bersaglio) is False

    def test_non_admin_non_puo_impersonare(self):
        segreteria = _persona("seg@campania.agesci.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        bersaglio = _persona("cg@campania.agesci.it")
        assert puo_impersonare(hijacker=segreteria, hijacked=bersaglio) is False

    def test_non_puo_impersonare_se_stesso(self):
        admin = _persona("admin@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        assert puo_impersonare(hijacker=admin, hijacked=admin) is False


class TestPuoImpersonareQualcuno:
    def test_admin_reale_puo_impersonare_qualcuno(self):
        admin = _persona("admin@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        assert puo_impersonare_qualcuno(admin) is True

    def test_superuser_puo_impersonare_qualcuno(self):
        superuser = _persona("root@campania.agesci.it", is_superuser=True)
        assert puo_impersonare_qualcuno(superuser) is True

    def test_admin_per_delega_non_puo_impersonare_qualcuno(self):
        titolare = _persona("titolare2@campania.agesci.it")
        ruolo_admin = Ruolo.objects.create(utente=titolare, tipo=Ruolo.Tipo.ADMIN)
        delegato = _persona("delegato2@campania.agesci.it")
        crea_delega(
            delegante=titolare,
            ruolo=ruolo_admin,
            email_delegato=delegato.email,
            data_fine=DOMANI,
        )
        assert puo_impersonare_qualcuno(delegato) is False

    def test_non_admin_non_puo_impersonare_qualcuno(self):
        segreteria = _persona("seg2@campania.agesci.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        assert puo_impersonare_qualcuno(segreteria) is False


@pytest.mark.django_db
class TestImpersonaListaView:
    def test_accesso_negato_senza_ruolo_admin(self, client):
        segreteria = _persona("seg3@campania.agesci.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        client.force_login(segreteria)
        response = client.get("/accounts/impersona/")
        assert response.status_code == 403

    def test_accesso_negato_anonimo(self, client):
        response = client.get("/accounts/impersona/")
        assert response.status_code == 302

    def test_senza_query_non_mostra_risultati(self, client):
        admin = _persona("admin3@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        client.force_login(admin)
        response = client.get("/accounts/impersona/")
        assert response.status_code == 200
        assert list(response.context["risultati"]) == []

    def test_ricerca_per_email_trova_lutente(self, client):
        admin = _persona("admin4@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        bersaglio = _persona("cercami@campania.agesci.it")
        client.force_login(admin)
        response = client.get("/accounts/impersona/", {"q": "cercami"})
        assert response.status_code == 200
        assert list(response.context["risultati"]) == [bersaglio]

    def test_ricerca_esclude_se_stesso(self, client):
        admin = _persona("admin5@campania.agesci.it")
        Ruolo.objects.create(utente=admin, tipo=Ruolo.Tipo.ADMIN)
        client.force_login(admin)
        response = client.get("/accounts/impersona/", {"q": "admin5"})
        assert response.status_code == 200
        assert list(response.context["risultati"]) == []


class TestAzioniPrecluse:
    def test_azione_preclusa_solleva_permission_denied_in_hijack(self):
        @vieta_in_impersonificazione("modifica_password")
        def cambia_password(request):
            return "ok"

        request = FakeRequest(session={"hijack_history": ["1"]})
        with pytest.raises(PermissionDenied):
            cambia_password(request)

    def test_azione_consentita_fuori_da_hijack(self):
        @vieta_in_impersonificazione("modifica_password")
        def cambia_password(request):
            return "ok"

        request = FakeRequest(session={})
        assert cambia_password(request) == "ok"

    def test_azione_non_riconosciuta_solleva_value_error(self):
        with pytest.raises(ValueError):
            vieta_in_impersonificazione("azione-inesistente")


class TestSessioneImpersonificazione:
    def test_hijack_started_crea_la_sessione(self):
        admin = _persona("admin@campania.agesci.it")
        bersaglio = _persona("cg@campania.agesci.it")
        request = FakeRequest()

        hijack_started.send(sender=None, request=request, hijacker=admin, hijacked=bersaglio)

        sessione = SessioneImpersonificazione.objects.get(
            amministratore=admin, utente_impersonato=bersaglio
        )
        assert sessione.terminata_il is None
        assert sessione.ip == "127.0.0.1"

    def test_hijack_ended_chiude_la_sessione_e_notifica(self):
        admin = _persona("admin2@campania.agesci.it")
        bersaglio = _persona("cg2@campania.agesci.it")
        request = FakeRequest()

        hijack_started.send(sender=None, request=request, hijacker=admin, hijacked=bersaglio)
        mail.outbox.clear()
        hijack_ended.send(sender=None, request=request, hijacker=admin, hijacked=bersaglio)

        sessione = SessioneImpersonificazione.objects.get(
            amministratore=admin, utente_impersonato=bersaglio
        )
        assert sessione.terminata_il is not None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [bersaglio.email]
