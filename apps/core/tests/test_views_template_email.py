"""Viste "Template email" (M8.4): permessi (solo RUOLI_GESTIONE_IMPOSTAZIONI
diretti, D-11), anteprima senza salvataggio, invio di test riusa
invia_email_template (nessun percorso parallelo), auditlog."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import mail

from apps.accounts.models import Delega, Ruolo, StatoUtente, TipoUtente, Utente
from apps.core.models import CodiceTemplateEmail, TemplateEmail
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


@pytest.fixture
def template_delega_creata() -> TemplateEmail:
    return TemplateEmail.objects.get(codice=CodiceTemplateEmail.DELEGA_CREATA)


class TestPermessi:
    def test_anonimo_non_accede_alla_lista(self, client):
        response = client.get("/impostazioni/template-email/")
        assert response.status_code == 302

    def test_cg_non_autorizzato(self, client, template_delega_creata):
        utente = _persona("cg@campania.agesci.it")
        _con_mfa_configurata(utente)
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        client.force_login(utente)

        assert client.get("/impostazioni/template-email/").status_code == 403
        assert (
            client.get(f"/impostazioni/template-email/{template_delega_creata.pk}/").status_code
            == 403
        )

    def test_delegato_di_segreteria_non_modifica(self, client, segreteria, template_delega_creata):
        # D-11: stesso perimetro di ImpostazioniPiattaforma, esclusi i delegati.
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

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {"azione": "salva", "oggetto": "Non deve passare", "corpo_html": "", "corpo_testo": ""},
        )
        assert response.status_code == 403

    def test_segreteria_diretta_accede_e_modifica(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "salva",
                "oggetto": "Oggetto aggiornato",
                "corpo_html": "<p>Ciao</p>",
                "corpo_testo": "Ciao",
            },
        )

        assert response.status_code == 302
        template_delega_creata.refresh_from_db()
        assert template_delega_creata.oggetto == "Oggetto aggiornato"


class TestSubjectPrefixNonInOggetto:
    def test_subject_prefix_in_oggetto_rifiutato(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)
        oggetto_originale = template_delega_creata.oggetto

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "salva",
                "oggetto": "{{ subjectPrefix }} Delega creata",
                "corpo_html": "",
                "corpo_testo": "",
            },
        )

        assert response.status_code == 200
        assert response.context["form"].errors.get("oggetto")
        template_delega_creata.refresh_from_db()
        assert template_delega_creata.oggetto == oggetto_originale

    def test_subject_prefix_nel_corpo_e_ammesso(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "salva",
                "oggetto": "Delega creata",
                "corpo_html": "",
                "corpo_testo": "Un saluto da {{ subjectPrefix }}.",
            },
        )

        assert response.status_code == 302
        template_delega_creata.refresh_from_db()
        assert template_delega_creata.corpo_testo == "Un saluto da {{ subjectPrefix }}."


class TestAnteprima:
    def test_anteprima_non_salva(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)
        oggetto_originale = template_delega_creata.oggetto

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "anteprima",
                "oggetto": "MAI SALVATO",
                "corpo_html": "<p>{{ ruolo }}</p>",
                "corpo_testo": "{{ ruolo }}",
            },
        )

        assert response.status_code == 200
        assert "anteprima" in response.context
        template_delega_creata.refresh_from_db()
        assert template_delega_creata.oggetto == oggetto_originale

    def test_anteprima_sostituisce_le_variabili_di_esempio(
        self, client, segreteria, template_delega_creata
    ):
        client.force_login(segreteria)

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "anteprima",
                "oggetto": "Oggetto",
                "corpo_html": "<p>Ruolo: {{ ruolo }}</p>",
                "corpo_testo": "Ruolo: {{ ruolo }}",
            },
        )

        assert "{{ ruolo }}" not in response.context["anteprima"]["corpo_html"]
        assert "Ruolo:" in response.context["anteprima"]["corpo_testo"]


class TestInviaTest:
    def test_invia_test_a_se_stessi(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)
        mail.outbox.clear()

        response = client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "test",
                "oggetto": "Oggetto di test",
                "corpo_html": "<p>Ciao {{ delegato }}</p>",
                "corpo_testo": "Ciao {{ delegato }}",
            },
        )

        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [segreteria.email]
        assert mail.outbox[0].subject == "Oggetto di test"

    def test_invia_test_salva_prima_di_inviare(self, client, segreteria, template_delega_creata):
        # Decisione presa: "Invia test" riusa invia_email_template (nessun
        # percorso di invio parallelo), che legge sempre dal DB — quindi
        # salva il form prima di inviare.
        client.force_login(segreteria)

        client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "test",
                "oggetto": "Oggetto salvato da test",
                "corpo_html": "",
                "corpo_testo": "Testo",
            },
        )

        template_delega_creata.refresh_from_db()
        assert template_delega_creata.oggetto == "Oggetto salvato da test"


class TestAuditlog:
    def test_modifica_tracciata(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)

        client.post(
            f"/impostazioni/template-email/{template_delega_creata.pk}/",
            {
                "azione": "salva",
                "oggetto": "Oggetto tracciato",
                "corpo_html": "",
                "corpo_testo": "",
            },
        )

        ct = ContentType.objects.get_for_model(TemplateEmail)
        log = LogEntry.objects.filter(
            content_type=ct, object_id=str(template_delega_creata.pk)
        ).latest("timestamp")
        assert log.changes["oggetto"][1] == "Oggetto tracciato"


class TestLista:
    def test_lista_mostra_i_sei_template(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/impostazioni/template-email/")
        assert response.status_code == 200
        assert len(response.context["template_email"]) == 6

    def test_lista_ha_link_di_ritorno_a_impostazioni(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/impostazioni/template-email/")
        assert 'href="/impostazioni/"' in response.content.decode()


class TestBreadcrumb:
    def test_lista_breadcrumb(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/impostazioni/template-email/")
        assert response.context["breadcrumb_items"] == [
            {"label": "Home", "url": "/"},
            {"label": "Amministrazione"},
            {"label": "Impostazioni", "url": "/impostazioni/"},
            {"label": "Template email"},
        ]

    def test_modifica_breadcrumb(self, client, segreteria, template_delega_creata):
        client.force_login(segreteria)
        response = client.get(f"/impostazioni/template-email/{template_delega_creata.pk}/")
        assert response.context["breadcrumb_items"] == [
            {"label": "Home", "url": "/"},
            {"label": "Amministrazione"},
            {"label": "Impostazioni", "url": "/impostazioni/"},
            {"label": "Template email", "url": "/impostazioni/template-email/"},
            {"label": "Modifica template"},
        ]
