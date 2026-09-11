import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.middleware import MFAEnforcementMiddleware, StatoUtenteMiddleware
from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import AllowlistGruppo, Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


class DummyForm:
    def __init__(self, email):
        self.cleaned_data = {
            "email": email,
            "first_name": "",
            "last_name": "",
            "password1": "Segretissima!123",
        }


class TestCatelloAccountAdapter:
    def test_signup_con_email_in_allowlist_attiva_account_di_gruppo(self, gruppo):
        from apps.accounts.adapters import CatelloAccountAdapter

        AllowlistGruppo.objects.create(
            codice_gruppo=gruppo.codice, email="avellino1@campania.agesci.it"
        )

        adapter = CatelloAccountAdapter()
        utente = Utente(username="", email="")
        form = DummyForm("avellino1@campania.agesci.it")

        salvato = adapter.save_user(request=None, user=utente, form=form)

        assert salvato.stato == StatoUtente.ATTIVO
        assert salvato.tipo == TipoUtente.GRUPPO
        assert salvato.gruppo_id == gruppo.codice
        assert salvato.ruoli.filter(tipo=Ruolo.Tipo.CG, gruppo=gruppo).exists()

    def test_signup_senza_allowlist_resta_in_attesa(self):
        from apps.accounts.adapters import CatelloAccountAdapter

        adapter = CatelloAccountAdapter()
        utente = Utente(username="", email="")
        form = DummyForm("mario.rossi@example.com")

        salvato = adapter.save_user(request=None, user=utente, form=form)

        assert salvato.stato == StatoUtente.IN_ATTESA
        assert salvato.tipo == TipoUtente.PERSONA
        assert salvato.ruoli.count() == 0


class TestStatoUtenteMiddleware:
    def test_utente_in_attesa_viene_rediretto(self, rf: RequestFactory):
        utente = Utente.objects.create(
            username="u", email="u@example.com", stato=StatoUtente.IN_ATTESA
        )
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = StatoUtenteMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 302
        assert response.url == "/accounts/attesa/"

    def test_utente_attivo_prosegue(self, rf: RequestFactory):
        utente = Utente.objects.create(
            username="u", email="u@example.com", stato=StatoUtente.ATTIVO
        )
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = StatoUtenteMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 200

    def test_percorso_escluso_non_viene_bloccato(self, rf: RequestFactory):
        utente = Utente.objects.create(
            username="u", email="u@example.com", stato=StatoUtente.IN_ATTESA
        )
        request = rf.get("/accounts/attesa/")
        request.user = utente

        middleware = StatoUtenteMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 200

    def test_utente_anonimo_non_viene_bloccato(self, rf: RequestFactory):
        request = rf.get("/qualsiasi-percorso/")
        request.user = AnonymousUser()

        middleware = StatoUtenteMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 200


class TestMFAEnforcementMiddleware:
    def test_ruolo_obbligato_senza_mfa_viene_rediretto(self, rf: RequestFactory, settings):
        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        utente = Utente.objects.create(
            username="a", email="a@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = MFAEnforcementMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 302
        assert response.url == "/accounts/2fa/"

    def test_ruolo_non_obbligato_prosegue(self, rf: RequestFactory, settings):
        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        utente = Utente.objects.create(
            username="cg", email="cg@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        gruppo = Gruppo.objects.create(codice="E0135", nome="AVELLINO 3")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = MFAEnforcementMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 200

    def test_admin_con_sola_passkey_non_viene_rediretto(self, rf: RequestFactory, settings):
        from allauth.mfa.models import Authenticator

        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN"}
        utente = Utente.objects.create(
            username="a", email="a@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.WEBAUTHN, data={})
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = MFAEnforcementMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 200

    def test_rdz_con_sola_passkey_viene_comunque_rediretto(self, rf: RequestFactory, settings):
        from allauth.mfa.models import Authenticator

        settings.RUOLI_MFA_OBBLIGATORIA = {"RDZ"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN", "SEGRETERIA"}
        utente = Utente.objects.create(
            username="r", email="r@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.WEBAUTHN, data={})
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = MFAEnforcementMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 302
        assert response.url == "/accounts/2fa/"

    def test_admin_e_rdz_diretti_la_passkey_basta(self, rf: RequestFactory, settings):
        """ADMIN/SEGRETERIA vincono sempre su RDZ quando coesistono (issue #10)."""
        from allauth.mfa.models import Authenticator

        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN", "RDZ"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN", "SEGRETERIA"}
        utente = Utente.objects.create(
            username="ar", email="ar@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.WEBAUTHN, data={})
        request = rf.get("/qualsiasi-percorso/")
        request.user = utente

        middleware = MFAEnforcementMiddleware(lambda r: HttpResponse("ok"))
        response = middleware(request)

        assert response.status_code == 200


class TestCanDeleteAuthenticator:
    def test_admin_non_puo_cancellare_unica_passkey(self, settings):
        from allauth.mfa.models import Authenticator

        from apps.accounts.adapters import CatelloMFAAdapter

        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN"}
        utente = Utente.objects.create(
            username="a", email="a@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
        passkey = Authenticator.objects.create(
            user=utente, type=Authenticator.Type.WEBAUTHN, data={}
        )

        assert CatelloMFAAdapter().can_delete_authenticator(passkey) is False

    def test_admin_puo_cancellare_passkey_se_ha_anche_totp(self, settings):
        from allauth.mfa.models import Authenticator

        from apps.accounts.adapters import CatelloMFAAdapter

        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN"}
        utente = Utente.objects.create(
            username="a", email="a@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
        passkey = Authenticator.objects.create(
            user=utente, type=Authenticator.Type.WEBAUTHN, data={}
        )
        Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})

        assert CatelloMFAAdapter().can_delete_authenticator(passkey) is True

    def test_recovery_codes_sempre_cancellabili(self, settings):
        from allauth.mfa.models import Authenticator

        from apps.accounts.adapters import CatelloMFAAdapter

        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN"}
        utente = Utente.objects.create(
            username="a", email="a@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.WEBAUTHN, data={})
        codici = Authenticator.objects.create(
            user=utente, type=Authenticator.Type.RECOVERY_CODES, data={}
        )

        assert CatelloMFAAdapter().can_delete_authenticator(codici) is True

    def test_rdz_non_puo_cancellare_unico_totp_anche_con_passkey(self, settings):
        """La passkey non conta per RDZ: resta vincolato al TOTP (issue #10)."""
        from allauth.mfa.models import Authenticator

        from apps.accounts.adapters import CatelloMFAAdapter

        settings.RUOLI_MFA_OBBLIGATORIA = {"RDZ"}
        settings.RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN", "SEGRETERIA"}
        utente = Utente.objects.create(
            username="r", email="r@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
        totp = Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
        Authenticator.objects.create(user=utente, type=Authenticator.Type.WEBAUTHN, data={})

        assert CatelloMFAAdapter().can_delete_authenticator(totp) is False

    def test_utente_senza_ruolo_obbligato_puo_cancellare_tutto(self, settings):
        from allauth.mfa.models import Authenticator

        from apps.accounts.adapters import CatelloMFAAdapter

        settings.RUOLI_MFA_OBBLIGATORIA = {"ADMIN"}
        utente = Utente.objects.create(
            username="u", email="u@campania.agesci.it", stato=StatoUtente.ATTIVO
        )
        totp = Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})

        assert CatelloMFAAdapter().can_delete_authenticator(totp) is True
