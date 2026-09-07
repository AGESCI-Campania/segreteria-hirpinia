"""Motore di sostituzione ridotto (M8.2): solo `{{ variabile }}`, nessun tag
Django, nessun placeholder mancante che blocchi l'output."""

from apps.core.models import CodiceTemplateEmail
from apps.core.template_email import contesto_esempio, sostituisci_placeholder


class TestSostituisciPlaceholder:
    def test_sostituisce_variabili_note(self):
        risultato = sostituisci_placeholder(
            "Ciao {{ nome }}, oggi è il {{ data }}.", {"nome": "Mario", "data": "01/01/2026"}
        )
        assert risultato == "Ciao Mario, oggi è il 01/01/2026."

    def test_placeholder_mancante_diventa_stringa_vuota(self):
        risultato = sostituisci_placeholder(
            "Ciao {{ nome }}, {{ sconosciuta }}!", {"nome": "Mario"}
        )
        assert risultato == "Ciao Mario, !"

    def test_tag_django_non_eseguito(self):
        # Un tag Django letterale nel testo (es. incollato per errore da un
        # admin) non deve mai essere interpretato: resta testo, non un tag.
        risultato = sostituisci_placeholder("{% if x %}pericoloso{% endif %}", {})
        assert risultato == "{% if x %}pericoloso{% endif %}"

    def test_spazi_intorno_al_nome_sono_ammessi(self):
        assert sostituisci_placeholder("{{nome}}-{{ nome }}-{{  nome  }}", {"nome": "X"}) == "X-X-X"

    def test_nessun_placeholder_testo_invariato(self):
        assert (
            sostituisci_placeholder("Testo semplice.", {"qualsiasi": "cosa"}) == "Testo semplice."
        )


class TestContestoEsempio:
    def test_link_invito_attivazione_usano_site_url(self, settings):
        settings.SITE_URL = "https://catello.example.org"
        contesto = contesto_esempio(CodiceTemplateEmail.INVITO_ATTIVAZIONE)

        assert contesto["link_attivazione"].startswith("https://catello.example.org/accounts/")
        assert contesto["link_recupero"].startswith("https://catello.example.org/accounts/")
        assert "https://catello.example.org/contributi/" in contesto["paragrafo_gruppo"]

    def test_link_invito_attivazione_seguono_site_url_configurato(self, settings):
        settings.SITE_URL = "https://segreteria.agescihirpinia.it"
        contesto = contesto_esempio(CodiceTemplateEmail.INVITO_ATTIVAZIONE)

        assert contesto["link_attivazione"].startswith("https://segreteria.agescihirpinia.it/")
        assert contesto["link_recupero"].startswith("https://segreteria.agescihirpinia.it/")
        assert "https://segreteria.agescihirpinia.it/" in contesto["paragrafo_gruppo"]

    def test_codice_senza_contesto_di_esempio_restituisce_dizionario_vuoto(self):
        assert contesto_esempio("codice-inesistente") == {}
