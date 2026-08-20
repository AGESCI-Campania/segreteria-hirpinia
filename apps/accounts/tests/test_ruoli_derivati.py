"""Sincronizzazione del ruolo CG con l'incarico di capogruppo (D-30)."""

import datetime

import pytest
from django.core import mail

from apps.accounts.models import Delega, Ruolo, TipoUtente, Utente
from apps.accounts.ruoli_derivati import sincronizza_ruoli_cg
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

OGGI = datetime.date.today()
FRA_UN_ANNO = OGGI + datetime.timedelta(days=365)


def _persona(email: str) -> Utente:
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def utente() -> Utente:
    return _persona("cg@campania.agesci.it")


class TestSincronizzaRuoliCG:
    def test_nessuna_operazione_se_utente_none(self, gruppo):
        sincronizza_ruoli_cg(utente=None, gruppi_capogruppo=frozenset({gruppo.codice}))
        assert Ruolo.objects.count() == 0

    def test_apre_ruolo_cg_derivato(self, utente, gruppo):
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))

        ruolo = Ruolo.objects.get(utente=utente)
        assert ruolo.tipo == Ruolo.Tipo.CG
        assert ruolo.gruppo_id == gruppo.codice
        assert ruolo.origine == Ruolo.Origine.DERIVATO
        assert ruolo.attivo is True

    def test_non_duplica_se_gia_aperto(self, utente, gruppo):
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))

        assert Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.CG, attivo=True).count() == 1

    def test_chiude_ruolo_su_gruppo_lasciato_e_ne_apre_uno_nuovo(
        self, utente, gruppo, altro_gruppo
    ):
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))

        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({altro_gruppo.codice}))

        vecchio = Ruolo.objects.get(utente=utente, gruppo=gruppo)
        assert vecchio.attivo is False
        assert vecchio.data_fine == OGGI

        nuovo = Ruolo.objects.get(utente=utente, gruppo=altro_gruppo, attivo=True)
        assert nuovo.origine == Ruolo.Origine.DERIVATO

    def test_gestisce_piu_gruppi_capogruppo_contemporanei(self, utente, gruppo, altro_gruppo):
        sincronizza_ruoli_cg(
            utente=utente, gruppi_capogruppo=frozenset({gruppo.codice, altro_gruppo.codice})
        )

        attivi = Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.CG, attivo=True)
        assert {r.gruppo_id for r in attivi} == {gruppo.codice, altro_gruppo.codice}

    def test_chiusura_revoca_a_cascata_le_deleghe(self, utente, gruppo):
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))
        ruolo = Ruolo.objects.get(utente=utente)
        delegato = _persona("delegato@campania.agesci.it")
        delega = Delega.objects.create(
            delegante=utente, delegato=delegato, ruolo=ruolo, data_fine=FRA_UN_ANNO
        )
        mail.outbox.clear()

        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset())

        delega.refresh_from_db()
        assert delega.attiva is False
        assert len(mail.outbox) == 1

    def test_nessun_gruppo_capogruppo_chiude_tutto(self, utente, gruppo):
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))

        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset())

        assert Ruolo.objects.filter(utente=utente, attivo=True).count() == 0
        assert Ruolo.objects.filter(utente=utente, attivo=False).count() == 1
