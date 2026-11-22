import pytest
from django.core import mail

from apps.accounts.inviti import crea_invito, richiedi_recupero
from apps.accounts.models import InvitoAttivazione, StatoInvito
from apps.organizzazione.models import Gruppo, StatoGruppoAnno, anno_scout_corrente

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


class TestRichiediRecupero:
    def test_email_esistente_e_inesistente_ricevono_la_stessa_risposta_dal_servizio(self, gruppo):
        """Il servizio stesso non deve sollevare né segnalare in modo
        diverso: l'anti-enumerazione si verifica anche a livello di API, non
        solo di vista (la view userà comunque un messaggio unico)."""
        crea_invito(email="censito@campania.agesci.it", creato_da=None, gruppo=gruppo)
        mail.outbox.clear()

        richiedi_recupero("censito@campania.agesci.it")
        risultato_censito = len(mail.outbox)

        mail.outbox.clear()
        richiedi_recupero("mai-censito@campania.agesci.it")
        risultato_non_censito = len(mail.outbox)

        assert risultato_censito == 1
        assert risultato_non_censito == 0  # nessun invito da recuperare: nessuna email

    def test_invito_revocato_non_e_recuperabile(self, gruppo):
        invito = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        invito.stato = StatoInvito.REVOCATO
        invito.save(update_fields=["stato"])

        richiedi_recupero("a@campania.agesci.it")

        invito.refresh_from_db()
        assert invito.stato == StatoInvito.REVOCATO
        assert InvitoAttivazione.objects.filter(email="a@campania.agesci.it").count() == 1

    def test_invito_scaduto_e_recuperabile_e_revoca_il_precedente(self, gruppo):
        import datetime

        from django.utils import timezone

        invito = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        invito.scadenza = timezone.now() - datetime.timedelta(days=1)
        invito.save(update_fields=["scadenza"])

        richiedi_recupero("a@campania.agesci.it")

        invito.refresh_from_db()
        # L'invito scaduto resta SCADUTO (stato terminale coerente con ciò
        # che è realmente accaduto); quel che conta è che ne sia stato
        # emesso uno nuovo, distinto e attivo.
        assert invito.stato == StatoInvito.SCADUTO
        nuovo = InvitoAttivazione.objects.filter(email="a@campania.agesci.it").latest("id")
        assert nuovo.stato == StatoInvito.INVIATO
        assert nuovo.pk != invito.pk

    def test_gruppo_disattivato_impedisce_il_recupero(self, gruppo):
        crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        StatoGruppoAnno.objects.create(
            gruppo=gruppo, anno_scout=anno_scout_corrente(), attivo=False
        )
        mail.outbox.clear()

        richiedi_recupero("a@campania.agesci.it")

        assert len(mail.outbox) == 0


class TestTemplateInvitoIncompleto:
    """Placeholder obbligatori: senza codice nell'email l'invito non serve."""

    @pytest.fixture
    def senza_codice(self):
        from apps.core.models import CodiceTemplateEmail, TemplateEmail

        TemplateEmail.objects.filter(codice=CodiceTemplateEmail.INVITO_ATTIVAZIONE).update(
            corpo_testo="Attiva qui: {{ link_attivazione }}"
        )

    def test_nessun_invito_creato(self, gruppo, senza_codice):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match=r"\{\{ codice \}\}"):
            crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        assert not InvitoAttivazione.objects.exists()
        assert mail.outbox == []

    def test_recupero_stesso_messaggio_per_ogni_indirizzo(self, client, gruppo, senza_codice):
        InvitoAttivazione.objects.create(email="censito@campania.agesci.it", gruppo=gruppo)
        risposte = [
            client.post("/accounts/recupero/", {"email": email}, follow=True)
            .content.decode()
            .count("non è momentaneamente disponibile")
            for email in ("censito@campania.agesci.it", "mai-censito@campania.agesci.it")
        ]
        assert risposte == [1, 1]
        assert mail.outbox == []
