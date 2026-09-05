"""Impostazioni di piattaforma (A-5): singleton, perimetro D-11 (esclusi i
delegati), tracciamento in auditlog."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Delega, Ruolo, StatoUtente, TipoUtente, Utente
from apps.core.models import ImpostazioniPiattaforma
from apps.organizzazione.models import Gruppo

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


class TestSingleton:
    def test_corrente_crea_la_riga_1(self):
        impostazioni = ImpostazioniPiattaforma.corrente()
        assert impostazioni.pk == 1
        assert ImpostazioniPiattaforma.objects.count() == 1

    def test_corrente_riusa_la_stessa_riga(self):
        prima = ImpostazioniPiattaforma.corrente()
        prima.causale_bonifico_default = "Causale di prova"
        prima.save()

        seconda = ImpostazioniPiattaforma.corrente()

        assert seconda.pk == prima.pk
        assert seconda.causale_bonifico_default == "Causale di prova"
        assert ImpostazioniPiattaforma.objects.count() == 1


class TestPermessi:
    def test_anonimo_non_accede(self, client):
        response = client.get("/impostazioni/")
        assert response.status_code == 302

    def test_cg_non_autorizzato(self, client):
        utente = _persona("cg@campania.agesci.it")
        _con_mfa_configurata(utente)
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        client.force_login(utente)
        response = client.get("/impostazioni/")
        assert response.status_code == 403

    def test_segreteria_diretta_accede_e_modifica(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post("/impostazioni/", {"causale_bonifico_default": "Nuova causale"})
        assert response.status_code == 302
        assert ImpostazioniPiattaforma.corrente().causale_bonifico_default == "Nuova causale"

    def test_delegato_di_segreteria_non_modifica(self, client, segreteria):
        # D-11: stesso perimetro dei parametri di campagna, esclusi i delegati.
        delegato = _persona("delegato@campania.agesci.it")
        _con_mfa_configurata(delegato)
        ruolo = Ruolo.objects.get(utente=segreteria)
        Delega.objects.create(
            delegante=segreteria,
            delegato=delegato,
            ruolo=ruolo,
            data_fine=datetime.date.today() + datetime.timedelta(days=30),
        )
        client.force_login(delegato)
        response = client.post("/impostazioni/", {"causale_bonifico_default": "Non deve passare"})
        assert response.status_code == 403


class TestEmailSuMailpit:
    def test_attivazione_rifiutata_senza_host_configurato(self, client, segreteria, settings):
        settings.EMAIL_MAILPIT_HOST = ""
        client.force_login(segreteria)
        response = client.post(
            "/impostazioni/", {"causale_bonifico_default": "", "email_su_mailpit": "on"}
        )
        assert response.status_code == 200  # form non valido, ripresentato
        assert not ImpostazioniPiattaforma.corrente().email_su_mailpit

    def test_attivazione_accettata_con_host_configurato(self, client, segreteria, settings):
        settings.EMAIL_MAILPIT_HOST = "localhost"
        client.force_login(segreteria)
        response = client.post(
            "/impostazioni/", {"causale_bonifico_default": "", "email_su_mailpit": "on"}
        )
        assert response.status_code == 302
        assert ImpostazioniPiattaforma.corrente().email_su_mailpit


class TestPrefissoEFirma:
    def test_prefisso_e_firma_salvati(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post(
            "/impostazioni/",
            {
                "causale_bonifico_default": "",
                "prefisso_oggetto_email": "Zona Hirpinia",
                "firma_html": "<p>Segreteria</p>",
                "firma_testo": "Segreteria",
            },
        )
        assert response.status_code == 302
        impostazioni = ImpostazioniPiattaforma.corrente()
        assert impostazioni.prefisso_oggetto_email == "Zona Hirpinia"
        assert impostazioni.firma_html == "<p>Segreteria</p>"
        assert impostazioni.firma_testo == "Segreteria"


class TestAuditlog:
    def test_modifica_tracciata(self, client, segreteria):
        ImpostazioniPiattaforma.corrente()  # crea la riga con il default
        client.force_login(segreteria)
        client.post("/impostazioni/", {"causale_bonifico_default": "Causale tracciata"})

        ct = ContentType.objects.get_for_model(ImpostazioniPiattaforma)
        log = LogEntry.objects.filter(content_type=ct, object_id="1").latest("timestamp")
        assert log.changes["causale_bonifico_default"][1] == "Causale tracciata"
