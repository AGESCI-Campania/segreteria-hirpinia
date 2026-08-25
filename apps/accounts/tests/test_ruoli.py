"""Creazione e revoca di un ruolo esplicito (D-35, M11)."""

import datetime

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Delega, Ruolo, TipoUtente, Utente
from apps.accounts.ruoli import crea_ruolo_esplicito, revoca_ruolo_esplicito
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

OGGI = datetime.date.today()
FRA_UN_ANNO = OGGI + datetime.timedelta(days=365)


def _persona(email: str) -> Utente:
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def e9001() -> Gruppo:
    # Seminato dalla migrazione dati 0002_seed_e9001 (D-33): esiste sempre.
    return Gruppo.objects.get(codice="E9001")


@pytest.fixture
def admin() -> Utente:
    u = _persona("admin@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.ADMIN)
    return u


@pytest.fixture
def rdz() -> Utente:
    u = _persona("rdz@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.RDZ)
    return u


class TestRevocaRuoloEsplicito:
    def test_chiude_il_ruolo(self, admin, rdz):
        ruolo = rdz.ruoli.get()

        revoca_ruolo_esplicito(utente=admin, ruolo=ruolo)

        ruolo.refresh_from_db()
        assert ruolo.attivo is False
        assert ruolo.data_fine == OGGI

    def test_cascata_sulle_deleghe(self, admin, rdz):
        ruolo = rdz.ruoli.get()
        delegato = _persona("delegato@campania.agesci.it")
        delega = Delega.objects.create(
            delegante=rdz, delegato=delegato, ruolo=ruolo, data_fine=FRA_UN_ANNO
        )
        mail.outbox.clear()

        revoca_ruolo_esplicito(utente=admin, ruolo=ruolo)

        delega.refresh_from_db()
        assert delega.attiva is False
        assert len(mail.outbox) == 1

    def test_revoca_rdz_chiude_cg_derivato_su_e9001(self, admin, rdz, e9001):
        from apps.accounts.ruoli_derivati import sincronizza_cg_comitato_zona

        sincronizza_cg_comitato_zona(utente=rdz)
        ruolo_rdz = rdz.ruoli.get(tipo=Ruolo.Tipo.RDZ)

        revoca_ruolo_esplicito(utente=admin, ruolo=ruolo_rdz)

        cg_e9001 = Ruolo.objects.get(utente=rdz, tipo=Ruolo.Tipo.CG, gruppo=e9001)
        assert cg_e9001.attivo is False

    def test_revoca_ruolo_non_rdz_non_tocca_cg(self, admin):
        segreteria = _persona("segreteria@campania.agesci.it")
        ruolo = Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)

        revoca_ruolo_esplicito(utente=admin, ruolo=ruolo)

        ruolo.refresh_from_db()
        assert ruolo.attivo is False

    def test_permesso_negato_per_chi_non_ha_ruolo_di_gestione(self, rdz):
        persona = _persona("qualunque@campania.agesci.it")
        ruolo = rdz.ruoli.get()

        with pytest.raises(PermissionDenied):
            revoca_ruolo_esplicito(utente=persona, ruolo=ruolo)

    def test_permesso_negato_per_ruolo_di_gestione_solo_per_delega(self, admin, rdz):
        delegato = _persona("delegato-admin@campania.agesci.it")
        ruolo_admin = admin.ruoli.get()
        Delega.objects.create(
            delegante=admin, delegato=delegato, ruolo=ruolo_admin, data_fine=FRA_UN_ANNO
        )
        ruolo = rdz.ruoli.get()

        with pytest.raises(PermissionDenied):
            revoca_ruolo_esplicito(utente=delegato, ruolo=ruolo)

    def test_ruolo_derivato_non_si_revoca_direttamente(self, admin, rdz, e9001):
        from apps.accounts.ruoli_derivati import sincronizza_cg_comitato_zona

        sincronizza_cg_comitato_zona(utente=rdz)
        cg_derivato = Ruolo.objects.get(utente=rdz, tipo=Ruolo.Tipo.CG)

        with pytest.raises(ValueError):
            revoca_ruolo_esplicito(utente=admin, ruolo=cg_derivato)

    def test_ruolo_gia_chiuso_e_idempotente(self, admin, rdz):
        ruolo = rdz.ruoli.get()
        revoca_ruolo_esplicito(utente=admin, ruolo=ruolo)
        data_fine_prima = ruolo.data_fine

        revoca_ruolo_esplicito(utente=admin, ruolo=ruolo)

        ruolo.refresh_from_db()
        assert ruolo.data_fine == data_fine_prima


class TestCreaRuoloEsplicito:
    def test_crea_ruolo_semplice(self, admin):
        destinatario = _persona("dest@campania.agesci.it")

        ruolo = crea_ruolo_esplicito(
            utente_assegnante=admin, utente_destinatario=destinatario, tipo=Ruolo.Tipo.SEGRETERIA
        )

        assert ruolo.pk is not None
        assert ruolo.origine == Ruolo.Origine.AMMINISTRATIVO
        assert ruolo.assegnato_da == admin

    def test_cg_sempre_rifiutato(self, admin):
        destinatario = _persona("dest@campania.agesci.it")

        with pytest.raises(ValueError):
            crea_ruolo_esplicito(
                utente_assegnante=admin,
                utente_destinatario=destinatario,
                tipo=Ruolo.Tipo.CG,
            )
        assert not Ruolo.objects.filter(utente=destinatario, tipo=Ruolo.Tipo.CG).exists()

    def test_iabz_senza_branca_rifiutato(self, admin):
        destinatario = _persona("dest@campania.agesci.it")
        with pytest.raises(ValidationError):
            crea_ruolo_esplicito(
                utente_assegnante=admin, utente_destinatario=destinatario, tipo=Ruolo.Tipo.IABZ
            )

    def test_iabz_con_branca_ok(self, admin):
        destinatario = _persona("dest@campania.agesci.it")
        ruolo = crea_ruolo_esplicito(
            utente_assegnante=admin,
            utente_destinatario=destinatario,
            tipo=Ruolo.Tipo.IABZ,
            branca=Ruolo.Branca.LC,
        )
        assert ruolo.branca == Ruolo.Branca.LC

    def test_isz_senza_settore_rifiutato(self, admin):
        destinatario = _persona("dest@campania.agesci.it")
        with pytest.raises(ValidationError):
            crea_ruolo_esplicito(
                utente_assegnante=admin, utente_destinatario=destinatario, tipo=Ruolo.Tipo.ISZ
            )

    def test_isz_con_settore_ok(self, admin):
        destinatario = _persona("dest@campania.agesci.it")
        ruolo = crea_ruolo_esplicito(
            utente_assegnante=admin,
            utente_destinatario=destinatario,
            tipo=Ruolo.Tipo.ISZ,
            settore="Formazione",
        )
        assert ruolo.settore == "Formazione"

    def test_duplicato_rifiutato(self, admin):
        destinatario = _persona("dest@campania.agesci.it")
        crea_ruolo_esplicito(
            utente_assegnante=admin, utente_destinatario=destinatario, tipo=Ruolo.Tipo.SEGRETERIA
        )

        with pytest.raises(ValidationError):
            crea_ruolo_esplicito(
                utente_assegnante=admin,
                utente_destinatario=destinatario,
                tipo=Ruolo.Tipo.SEGRETERIA,
            )

    def test_rdz_sincronizza_cg_su_e9001(self, admin, e9001):
        destinatario = _persona("dest@campania.agesci.it")

        crea_ruolo_esplicito(
            utente_assegnante=admin, utente_destinatario=destinatario, tipo=Ruolo.Tipo.RDZ
        )

        cg_e9001 = Ruolo.objects.get(
            utente=destinatario, tipo=Ruolo.Tipo.CG, gruppo=e9001, origine=Ruolo.Origine.DERIVATO
        )
        assert cg_e9001.attivo is True

    def test_permesso_negato(self):
        estraneo = _persona("estraneo@campania.agesci.it")
        destinatario = _persona("dest@campania.agesci.it")

        with pytest.raises(PermissionDenied):
            crea_ruolo_esplicito(
                utente_assegnante=estraneo,
                utente_destinatario=destinatario,
                tipo=Ruolo.Tipo.SEGRETERIA,
            )
