import datetime
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.inviti import (
    InvitoNonValidoError,
    crea_invito,
    invia_inviti_multipli,
    verifica_e_completa,
)
from apps.accounts.models import InvitoAttivazione, StatoInvito, StatoUtente
from apps.organizzazione.models import Gruppo

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
        with patch("apps.accounts.inviti.send_mail", side_effect=[Exception("boom"), None]):
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
