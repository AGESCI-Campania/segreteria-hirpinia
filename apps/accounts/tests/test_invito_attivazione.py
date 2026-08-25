import datetime
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.inviti import (
    InvitoNonValidoError,
    candidati_invito_massivo,
    crea_invito,
    invia_inviti_multipli,
    verifica_e_completa,
)
from apps.accounts.models import InvitoAttivazione, StatoInvito, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import AllowlistGruppo, Gruppo, StatoGruppoAnno, anno_scout_corrente

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


def _codice_inviato() -> str:
    """Il codice in chiaro compare solo nel corpo dell'email inviata."""
    corpo = mail.outbox[-1].body
    riga = [r for r in corpo.splitlines() if "Codice di attivazione" in r][0]
    return riga.split(":")[-1].strip()


class TestCreaInvito:
    def test_email_multipart_con_alternativa_html(self, gruppo):
        # M8: il template configurato ha sempre un corpo_html, l'email deve
        # sempre essere multipart testo+HTML.
        crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        messaggio = mail.outbox[-1]
        assert messaggio.alternatives
        assert messaggio.alternatives[0][1] == "text/html"

    def test_paragrafo_gruppo_presente_solo_se_invito_ha_gruppo(self, gruppo):
        crea_invito(email="con-gruppo@campania.agesci.it", creato_da=None, gruppo=gruppo)
        corpo_con_gruppo = mail.outbox[-1].body

        crea_invito(email="senza-gruppo@campania.agesci.it", creato_da=None, gruppo=None)
        corpo_senza_gruppo = mail.outbox[-1].body

        assert "contributo del tuo gruppo" in corpo_con_gruppo
        assert "contributo del tuo gruppo" not in corpo_senza_gruppo

    def test_link_attivazione_contiene_email_e_codice(self, gruppo):
        crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        codice = _codice_inviato()
        corpo = mail.outbox[-1].body
        assert f"codice={codice}" in corpo
        assert "email=a%40campania.agesci.it" in corpo or "email=a@campania.agesci.it" in corpo

    def test_codice_mai_leggibile_in_chiaro_dal_modello(self, gruppo):
        invito = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        codice = _codice_inviato()
        assert invito.codice_hash != codice
        assert codice not in invito.codice_hash

    def test_nuovo_invito_revoca_il_precedente(self, gruppo):
        primo = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        secondo = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)

        primo.refresh_from_db()
        assert primo.stato == StatoInvito.REVOCATO
        assert secondo.stato == StatoInvito.INVIATO

    def test_invio_massivo_non_si_interrompe_se_un_invio_fallisce(self, gruppo):
        voci = [
            {"email": "a@campania.agesci.it", "gruppo": gruppo},
            {"email": "b@campania.agesci.it", "gruppo": gruppo},
        ]
        with patch(
            "django.core.mail.message.EmailMessage.send",
            side_effect=[Exception("boom"), None],
        ):
            risultati = invia_inviti_multipli(voci, creato_da=None)

        assert risultati[0][1] is False
        assert risultati[1][1] is True
        # Il primo invito resta comunque creato, anche se l'invio è fallito.
        assert InvitoAttivazione.objects.filter(email="a@campania.agesci.it").exists()


class TestVerificaECompleta:
    def test_codice_scaduto_e_rifiutato_con_messaggio_generico(self, gruppo):
        invito = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        codice = _codice_inviato()
        invito.scadenza = timezone.now() - datetime.timedelta(days=1)
        invito.save(update_fields=["scadenza"])

        with pytest.raises(InvitoNonValidoError):
            verifica_e_completa(email=invito.email, codice=codice, password="Segretissima!123")

        invito.refresh_from_db()
        assert invito.stato == StatoInvito.SCADUTO

    def test_cinque_tentativi_errati_revocano_invito(self, gruppo):
        invito = crea_invito(email="a@campania.agesci.it", creato_da=None, gruppo=gruppo)
        for _ in range(InvitoAttivazione.MASSIMO_TENTATIVI):
            with pytest.raises(InvitoNonValidoError):
                verifica_e_completa(
                    email=invito.email, codice="XXXXXXXX", password="Segretissima!123"
                )
        invito.refresh_from_db()
        assert invito.stato == StatoInvito.REVOCATO

    def test_attivazione_valida_crea_utente_gruppo_con_ruolo_cg(self, gruppo):
        invito = crea_invito(email="capo@campania.agesci.it", creato_da=None, gruppo=gruppo)
        codice = _codice_inviato()

        utente = verifica_e_completa(email=invito.email, codice=codice, password="Segretissima!123")

        assert utente.stato == StatoUtente.ATTIVO
        assert utente.gruppo_id == gruppo.codice
        assert utente.check_password("Segretissima!123")
        assert utente.ruoli.filter(tipo="CG", gruppo=gruppo).exists()

        invito.refresh_from_db()
        assert invito.stato == StatoInvito.USATO
        assert invito.usato_il is not None

    def test_invito_inesistente_e_rifiutato(self):
        with pytest.raises(InvitoNonValidoError):
            verifica_e_completa(
                email="mai-invitato@campania.agesci.it",
                codice="ABCDEFGH",
                password="Segretissima!123",
            )


def _candidato_per(candidati, email):
    return next((c for c in candidati if c.voce.email == email), None)


class TestCandidatiInvitoMassivo:
    def test_voce_senza_utente_e_candidata(self, gruppo):
        voce = AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")

        candidato = _candidato_per(candidati_invito_massivo(), "a@x.it")

        assert candidato is not None
        assert candidato.voce == voce
        assert candidato.gruppo == gruppo

    def test_utente_con_accesso_e_escluso(self, gruppo):
        AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")
        Utente.objects.create(
            username="a@x.it",
            email="a@x.it",
            tipo=TipoUtente.GRUPPO,
            gruppo=gruppo,
            last_login=timezone.now(),
        )

        assert _candidato_per(candidati_invito_massivo(), "a@x.it") is None

    def test_utente_mai_acceduto_resta_candidato(self, gruppo):
        AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")
        Utente.objects.create(
            username="a@x.it", email="a@x.it", tipo=TipoUtente.GRUPPO, gruppo=gruppo
        )

        assert _candidato_per(candidati_invito_massivo(), "a@x.it") is not None

    def test_gruppo_disattivato_e_escluso(self, gruppo):
        AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")
        StatoGruppoAnno.objects.create(
            gruppo=gruppo, anno_scout=anno_scout_corrente(), attivo=False, motivo="test"
        )

        assert _candidato_per(candidati_invito_massivo(), "a@x.it") is None
