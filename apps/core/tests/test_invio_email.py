"""Renderer unico degli invii email (M8.3): fallback hardcoded, sanitizzazione
bleach, sempre multipart quando è configurato un corpo HTML."""

import pytest
from django.core import mail

from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail, TemplateEmail

pytestmark = pytest.mark.django_db


class TestContenutoDaTemplateConfigurato:
    def test_usa_il_record_esistente(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            oggetto="Oggetto personalizzato per {{ delegato }}",
            corpo_testo="Corpo personalizzato: {{ ruolo }}",
            corpo_html="<p>Corpo HTML: {{ ruolo }}</p>",
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        messaggio = mail.outbox[0]
        assert messaggio.subject == "Oggetto personalizzato per Mario Rossi"
        assert messaggio.body == "Corpo personalizzato: Capogruppo"
        assert messaggio.alternatives[0][0] == "<p>Corpo HTML: Capogruppo</p>"
        assert messaggio.alternatives[0][1] == "text/html"

    def test_senza_corpo_html_nessuna_alternativa(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(corpo_html="")

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].alternatives == []


class TestFallback:
    def test_record_mancante_usa_il_fallback_hardcoded(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).delete()

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi", "scadenza": "01/01/2027"},
        )

        messaggio = mail.outbox[0]
        assert messaggio.subject == "Catello — hai concesso una delega"
        assert "Capogruppo" in messaggio.body
        assert "Mario Rossi" in messaggio.body

    def test_record_vuoto_usa_il_fallback_hardcoded(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            oggetto="", corpo_testo="", corpo_html=""
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi", "scadenza": "01/01/2027"},
        )

        assert mail.outbox[0].subject == "Catello — hai concesso una delega"

    def test_nessun_destinatario_non_invia_nulla(self):
        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA, destinatari=[], contesto={}
        )
        assert mail.outbox == []


class TestSanitizzazione:
    def test_rimuove_script(self):
        # bleach con strip=True toglie il tag <script> (l'unico elemento che
        # potrebbe eseguire codice in un client email che lo permettesse):
        # il testo residuo (senza più alcun tag) non è più eseguibile.
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html="<p>Ciao</p><script>alert('x')</script>"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "<script>" not in html
        assert "</script>" not in html

    def test_rimuove_attributi_onerror(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<img src="x" onerror="alert(1)">'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "onerror" not in html

    def test_mantiene_markup_semantico_ammesso(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<p>Testo <strong>forte</strong> con <a href="https://example.com">link</a></p>'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "<strong>forte</strong>" in html
        assert 'href="https://example.com"' in html
