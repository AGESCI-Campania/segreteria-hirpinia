"""Sincronizzazione del ruolo CG con l'incarico di capogruppo (D-30)."""

import datetime

import pytest
from django.core import mail

from apps.accounts.models import Delega, Ruolo, TipoUtente, Utente
from apps.accounts.ruoli_derivati import sincronizza_cg_comitato_zona, sincronizza_ruoli_cg
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


@pytest.fixture
def e9001() -> Gruppo:
    # Seminato dalla migrazione dati 0002_seed_e9001 (D-33): esiste sempre.
    return Gruppo.objects.get(codice="E9001")


class TestSincronizzaCgComitatoZona:
    def test_apre_cg_derivato_su_e9001_per_rdz_diretto(self, utente, e9001):
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)

        sincronizza_cg_comitato_zona(utente=utente)

        ruolo = Ruolo.objects.get(utente=utente, tipo=Ruolo.Tipo.CG)
        assert ruolo.gruppo_id == "E9001"
        assert ruolo.origine == Ruolo.Origine.DERIVATO
        assert ruolo.attivo is True

    def test_non_duplica_se_gia_aperto(self, utente, e9001):
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)

        sincronizza_cg_comitato_zona(utente=utente)
        sincronizza_cg_comitato_zona(utente=utente)

        assert (
            Ruolo.objects.filter(
                utente=utente, tipo=Ruolo.Tipo.CG, gruppo=e9001, attivo=True
            ).count()
            == 1
        )

    def test_rdz_per_delega_non_apre_cg_derivato(self, utente, e9001, gruppo):
        titolare = _persona("rdz-titolare@campania.agesci.it")
        ruolo_rdz = Ruolo.objects.create(utente=titolare, tipo=Ruolo.Tipo.RDZ)
        Delega.objects.create(
            delegante=titolare, delegato=utente, ruolo=ruolo_rdz, data_fine=FRA_UN_ANNO
        )

        sincronizza_cg_comitato_zona(utente=utente)

        assert not Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.CG).exists()

    def test_chiude_cg_derivato_quando_rdz_termina(self, utente, e9001):
        ruolo_rdz = Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
        sincronizza_cg_comitato_zona(utente=utente)

        ruolo_rdz.attivo = False
        ruolo_rdz.save(update_fields=["attivo"])
        sincronizza_cg_comitato_zona(utente=utente)

        ruolo_cg = Ruolo.objects.get(utente=utente, tipo=Ruolo.Tipo.CG)
        assert ruolo_cg.attivo is False
        assert ruolo_cg.data_fine == OGGI

    def test_cg_su_e9001_coesiste_con_cg_su_gruppo_reale(self, utente, e9001, gruppo):
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
        sincronizza_ruoli_cg(utente=utente, gruppi_capogruppo=frozenset({gruppo.codice}))

        sincronizza_cg_comitato_zona(utente=utente)

        attivi = Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.CG, attivo=True)
        assert {r.gruppo_id for r in attivi} == {gruppo.codice, "E9001"}

    def test_nessun_gruppo_e9001_non_fa_nulla(self, utente):
        # Caso di rete di sicurezza: E9001 esiste sempre in pratica (seminato
        # dalla migrazione dati), ma la funzione non deve rompersi se manca.
        Gruppo.objects.filter(codice="E9001").delete()
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)

        sincronizza_cg_comitato_zona(utente=utente)

        assert not Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.CG).exists()
