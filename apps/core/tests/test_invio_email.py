"""Renderer unico degli invii email (M8.3): fallback hardcoded, sanitizzazione
bleach, sempre multipart quando è configurato un corpo HTML."""

import pytest
from django.core import mail

from apps.core.invio_email import invia_email_template, sanifica_html
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
        # <img> è ammesso da M-tabelle-immagini: il test deve verificare che
        # il tag sopravviva e solo l'attributo onerror venga rimosso,
        # altrimenti non prova nulla (prima di quella milestone passava per
        # il motivo sbagliato: <img> non era ammesso, spariva l'intero tag).
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<img src="https://example.com/x.png" onerror="alert(1)">'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "<img" in html
        assert "onerror" not in html
        assert 'src="https://example.com/x.png"' in html

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


class TestSanitizzazioneTabelleImmagini:
    """M-tabelle-immagini: allowlist verificata empiricamente contro il
    markup reale prodotto da TinyMCE 8.8.2 (vedi commento in
    apps/core/invio_email.py), non solo dedotta dalla documentazione."""

    def test_tabella_bordo_larghezza_e_colonne_sopravvivono(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html=(
                '<table style="width: 450px;" border="1">'
                '<colgroup><col style="width: 150px;"><col style="width: 300px;"></colgroup>'
                "<tbody><tr><td>A</td><td>B</td></tr></tbody></table>"
            )
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert 'style="width: 450px;"' in html
        assert 'border="1"' in html
        assert 'style="width: 150px;"' in html
        assert 'style="width: 300px;"' in html

    def test_td_con_colspan_e_rowspan_sopravvive(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<table><tr><td colspan="2" rowspan="3">A</td></tr></table>'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert 'colspan="2"' in html
        assert 'rowspan="3"' in html

    def test_stile_tabella_solo_width_ammesso(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<table style="width: 200px; background-color: red;"><tr><td>A</td></tr></table>'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "width: 200px" in html
        assert "background-color" not in html

    def test_proprieta_css_storicamente_pericolose_rimosse(self):
        # behavior/-moz-binding sono i vettori storici di CSS-XSS
        # (IE .htc, Firefox XBL): devono sparire anche se mescolati con
        # width nello stesso attributo style, mai fidarsi del solo fatto che
        # una proprietà ammessa sia presente nella stessa dichiarazione.
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html=(
                '<table style="width: 100px; behavior: url(evil.htc); '
                '-moz-binding: url(evil.xml);"><tr><td>A</td></tr></table>'
            )
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "width: 100px" in html
        assert "behavior" not in html
        assert "-moz-binding" not in html
        assert "evil" not in html

    def test_script_annidato_in_cella_rimosso(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html="<table><tr><td>A<script>alert(1)</script></td></tr></table>"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "<script>" not in html

    def test_immagine_con_src_valido_sopravvive(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<img src="https://example.com/x.png" alt="y" width="100" height="50">'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert '<img src="https://example.com/x.png" alt="y" width="100" height="50">' in html

    def test_immagine_con_protocollo_non_ammesso_perde_il_src(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html='<img src="javascript:alert(1)" alt="bad">'
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "javascript:" not in html
        assert "<img" in html


class TestNonRegressioneTemplateSeminati:
    """I 6 corpi seminati da apps/core/migrations/0003_seed_template_email.py
    non contengono tabelle/immagini: la nuova allowlist non deve cambiarne
    l'output rispetto a prima di M-tabelle-immagini (rete di sicurezza a
    basso costo, valori catturati con il codice reale prima della modifica)."""

    ATTESI = {
        CodiceTemplateEmail.DELEGA_CREATA: (
            "<p>Ciao,</p><p>hai concesso una delega per il ruolo {{ ruolo }} a "
            "{{ delegato }}, con scadenza {{ scadenza }}.</p><p>— Catello, AGESCI "
            "Zona Hirpinia</p>"
        ),
        CodiceTemplateEmail.DELEGA_REVOCATA: (
            "<p>Ciao,</p><p>la delega che avevi concesso per il ruolo {{ ruolo }} a "
            "{{ delegato }} è stata revocata{{ revocata_da_frase }}.</p><p>— Catello, "
            "AGESCI Zona Hirpinia</p>"
        ),
        CodiceTemplateEmail.FINE_IMPERSONIFICAZIONE: (
            "<p>Ciao,</p><p>ti informiamo che il {{ quando }} {{ amministratore }} "
            "ha concluso una sessione di assistenza sul tuo account Catello "
            "(impersonificazione).</p><p>Se non eri a conoscenza di questa richiesta "
            "di assistenza, contatta la segreteria di Zona.</p><p>— Catello, AGESCI "
            "Zona Hirpinia</p>"
        ),
        CodiceTemplateEmail.INCARICO_ASSEGNATO: (
            "<p>Ciao,</p><p>è stato assegnato manualmente un nuovo incarico:</p>"
            "<ul><li>Capo: {{ capo }}</li><li>Gruppo di servizio: "
            "{{ gruppo_servizio }}</li><li>Unità: {{ unita }}</li>"
            "<li>Funzione: {{ funzione }}</li><li>Assegnato da: "
            "{{ assegnato_da }}</li></ul><p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
        CodiceTemplateEmail.INCARICO_CESSATO: (
            "<p>Ciao,</p><p>è stato cessato un incarico assegnato manualmente:</p>"
            "<ul><li>Capo: {{ capo }}</li><li>Gruppo di servizio: "
            "{{ gruppo_servizio }}</li><li>Unità: {{ unita }}</li>"
            "<li>Funzione: {{ funzione }}</li></ul><p>— Catello, AGESCI Zona "
            "Hirpinia</p>"
        ),
        CodiceTemplateEmail.INVITO_ATTIVAZIONE: (
            "<p>Ciao,</p><p>la segreteria della Zona Hirpinia ti invita ad attivare "
            "il tuo account su Catello.</p><p>Codice di attivazione: "
            "<strong>{{ codice }}</strong></p><p>Per attivare l'account: "
            '<a href="{{ link_attivazione }}">{{ link_attivazione }}</a></p>'
            "<p>Il codice scade il {{ scadenza }}. Se nel frattempo scade, puoi "
            'richiederne uno nuovo dalla <a href="{{ link_recupero }}">pagina di '
            "recupero</a>.</p>{{ paragrafo_gruppo }}<p>Se non hai richiesto tu "
            "questo invito, ignora questa email.</p><p>— Catello, AGESCI Zona "
            "Hirpinia</p>"
        ),
    }

    def test_output_sanificato_invariato(self):
        for codice, atteso in self.ATTESI.items():
            corpo_html = TemplateEmail.objects.get(codice=codice).corpo_html
            assert sanifica_html(corpo_html) == atteso, codice
