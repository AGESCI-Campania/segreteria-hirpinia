"""Renderer unico degli invii email (M8.3): fallback hardcoded, sanitizzazione
bleach, sempre multipart quando è configurato un corpo HTML."""

import pytest
from django.core import mail
from django.core.exceptions import ValidationError

from apps.core.forms import TemplateEmailForm
from apps.core.invio_email import (
    html_senza_contenuto,
    invia_email_template,
    problemi_corpi,
    problemi_template,
    sanifica_html,
    verifica_template,
)
from apps.core.models import CodiceTemplateEmail, ImpostazioniPiattaforma, TemplateEmail

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
        assert messaggio.subject == "Segreteria — hai concesso una delega"
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

        assert mail.outbox[0].subject == "Segreteria — hai concesso una delega"

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


class TestPrefissoOggetto:
    def test_prefisso_configurato_antepone_all_oggetto(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"prefisso_oggetto_email": "Zona Hirpinia"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            oggetto="Delega creata"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].subject == "Zona Hirpinia - Delega creata"

    def test_prefisso_vuoto_non_modifica_oggetto(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"prefisso_oggetto_email": ""}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            oggetto="Delega creata"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].subject == "Delega creata"

    def test_prefisso_disponibile_come_variabile_nel_corpo(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"prefisso_oggetto_email": "Zona Hirpinia"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_testo="Un saluto da {{ subjectPrefix }}."
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert "Un saluto da Zona Hirpinia." in mail.outbox[0].body

    def test_prefisso_applicato_anche_al_fallback(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"prefisso_oggetto_email": "Zona Hirpinia"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).delete()

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi", "scadenza": "01/01/2027"},
        )

        assert mail.outbox[0].subject == "Zona Hirpinia - Segreteria — hai concesso una delega"


class TestFirmaComune:
    def test_firma_testo_aggiunta_in_coda(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"firma_testo": "Cordiali saluti,\nSegreteria di Zona"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_testo="Corpo del messaggio."
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].body == (
            "Corpo del messaggio.\n\nCordiali saluti,\nSegreteria di Zona"
        )

    def test_firma_html_aggiunta_in_coda_e_sanificata(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"firma_html": "<p>Saluti</p><script>alert(1)</script>"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html="<p>Corpo</p>"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        html = mail.outbox[0].alternatives[0][0]
        assert "<script>" not in html
        assert html.startswith("<p>Corpo</p><p>Saluti</p>")

    def test_firma_html_senza_corpo_html_nessuna_alternativa(self):
        """Una versione HTML con la sola firma nasconderebbe il corpo testo,
        perché i programmi di posta mostrano l'HTML."""
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"firma_html": "<p>Solo firma</p>"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html="", corpo_testo="Corpo testuale"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].alternatives == []
        assert mail.outbox[0].body.startswith("Corpo testuale")

    def test_nessuna_firma_configurata_nessun_cambiamento(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"firma_testo": "", "firma_html": ""}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_testo="Corpo del messaggio.", corpo_html=""
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].body == "Corpo del messaggio."
        assert mail.outbox[0].alternatives == []


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


def test_template_codice_voto_seminato_uguale_al_fallback():
    """Il seed di 0017 deve cambiare solo la visibilità in Impostazioni, non
    l'email inviata: stesso testo del file di fallback e niente HTML."""
    from django.template.loader import get_template

    template = TemplateEmail.objects.get(codice=CodiceTemplateEmail.CODICE_VOTO)
    sorgente = get_template("voto/email/codice_voto.txt").template.source

    assert template.oggetto == "Catello — il tuo codice di voto"
    assert template.corpo_testo == sorgente
    assert template.corpo_html == ""


class TestHtmlSenzaContenuto:
    """Un HTML che non mostra nulla non si invia: i programmi di posta lo
    mostrerebbero al posto del testo (assemblea di Zona del 22/11/2026)."""

    @pytest.mark.parametrize("corpo", ["", "   ", "<p></p>", "<p>&nbsp;</p>", "<p>\xa0</p><br>"])
    def test_vuoti(self, corpo):
        assert html_senza_contenuto(corpo)

    @pytest.mark.parametrize("corpo", ["<p>Ciao</p>", '<p><img src="x.png"></p>', "{{ codice }}"])
    def test_con_contenuto(self, corpo):
        assert not html_senza_contenuto(corpo)

    def test_html_vuoto_con_firma_nessuna_alternativa(self):
        ImpostazioniPiattaforma.objects.update_or_create(
            pk=1, defaults={"firma_html": "<p>Solo firma</p>"}
        )
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.DELEGA_CREATA).update(
            corpo_html="<p>&nbsp;</p>", corpo_testo="Corpo testuale"
        )

        invia_email_template(
            codice_template=CodiceTemplateEmail.DELEGA_CREATA,
            destinatari=["mario@campania.agesci.it"],
            contesto={"ruolo": "Capogruppo", "delegato": "Mario Rossi"},
        )

        assert mail.outbox[0].alternatives == []


class TestPlaceholderObbligatori:
    """Regola generale: senza i placeholder di `PLACEHOLDER_OBBLIGATORI`
    l'email non serve al suo scopo e l'azione non procede."""

    VOTO = CodiceTemplateEmail.CODICE_VOTO

    def test_template_predefinito_va_bene(self):
        assert problemi_template(self.VOTO) == []

    def test_corpi_vuoti_usano_il_predefinito(self):
        assert problemi_corpi(self.VOTO, "", "") == []

    def test_manca_nel_testo(self):
        assert problemi_corpi(self.VOTO, "Ciao {{ nome }}", "") == [
            "il testo dell'email non contiene {{ codice }}"
        ]

    def test_manca_nell_html(self):
        assert problemi_corpi(self.VOTO, "Codice: {{codice}}", "<p>Ciao</p>") == [
            "la versione HTML dell'email non contiene {{ codice }}"
        ]

    def test_html_vuoto_non_conta(self):
        assert problemi_corpi(self.VOTO, "Codice: {{ codice }}", "<p>&nbsp;</p>") == []

    def test_template_senza_obbligatori(self):
        assert problemi_corpi(CodiceTemplateEmail.DELEGA_CREATA, "Ciao", "<p>Ciao</p>") == []

    def test_dal_database(self):
        TemplateEmail.objects.filter(codice=self.VOTO).update(corpo_html="<p>Solo firma</p>")
        assert problemi_template(self.VOTO) == [
            "la versione HTML dell'email non contiene {{ codice }}"
        ]

    def test_il_form_non_salva(self):
        template = TemplateEmail.objects.get(codice=self.VOTO)
        form = TemplateEmailForm(
            data={"oggetto": "Codice", "corpo_testo": "Ciao {{ nome }}", "corpo_html": ""},
            instance=template,
        )
        assert not form.is_valid()
        assert "{{ codice }}" in str(form.non_field_errors())

    def test_il_form_salva_con_il_codice(self):
        template = TemplateEmail.objects.get(codice=self.VOTO)
        form = TemplateEmailForm(
            data={
                "oggetto": "Codice",
                "corpo_testo": "Codice: {{ codice }}",
                "corpo_html": "<p>Codice: <strong>{{ codice }}</strong></p>",
            },
            instance=template,
        )
        assert form.is_valid(), form.errors


class TestPlaceholderObbligatoriTuttiITemplate:
    """Elenco deciso con Andrea il 22/11/2026 (PLACEHOLDER_OBBLIGATORI)."""

    @pytest.mark.parametrize("codice", list(CodiceTemplateEmail))
    def test_i_template_seminati_vanno_bene(self, codice):
        assert problemi_template(codice) == []

    @pytest.mark.parametrize("codice", list(CodiceTemplateEmail))
    def test_i_testi_predefiniti_vanno_bene(self, codice):
        from apps.core.invio_email import _contenuto_fallback

        _, testo = _contenuto_fallback(codice)
        assert problemi_corpi(codice, testo, "") == []

    def test_alternative_elenco_e_elenco_html(self):
        promemoria = CodiceTemplateEmail.NOTA_SPESE_PROMEMORIA
        assert (
            problemi_corpi(
                promemoria, "{{ elenco }} {{ link }}", "<div>{{ elenco_html }}</div>{{ link }}"
            )
            == []
        )
        assert problemi_corpi(promemoria, "{{ link }}", "") == [
            "il testo dell'email non contiene {{ elenco }} o {{ elenco_html }}"
        ]

    def test_verifica_template_nomina_il_template(self):
        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.NOTA_SPESE_RESPINTA).update(
            corpo_testo="Respinta."
        )
        with pytest.raises(ValidationError, match="«Nota spese — respinta»"):
            verifica_template(CodiceTemplateEmail.NOTA_SPESE_RESPINTA, cosa="Non si può")
