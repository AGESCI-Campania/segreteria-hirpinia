import datetime

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.deleghe import crea_delega, revoca_delega, revoca_deleghe_di_ruolo
from apps.accounts.models import Delega, Ruolo, TipoUtente, Utente
from apps.accounts.permessi import ruoli_effettivi
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

OGGI = datetime.date.today()
DOMANI = OGGI + datetime.timedelta(days=1)
FRA_UN_ANNO = OGGI + datetime.timedelta(days=365)


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


def _persona(email):
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def delegante(gruppo):
    u = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return u


@pytest.fixture
def ruolo_delegante(delegante):
    return delegante.ruoli.get()


class TestCreaDelega:
    def test_delega_valida_verso_utente_esistente(self, delegante, ruolo_delegante):
        delegato = _persona("delegato@campania.agesci.it")
        delega = crea_delega(
            delegante=delegante,
            ruolo=ruolo_delegante,
            email_delegato=delegato.email,
            data_fine=DOMANI,
        )
        assert delega.delegato_id == delegato.id
        assert delega.attiva is True
        assert any(r.tipo == Ruolo.Tipo.CG for r in ruoli_effettivi(delegato))

    def test_delega_verso_email_nuova_crea_utente_in_attesa_e_invito(
        self, delegante, ruolo_delegante
    ):
        from apps.accounts.models import InvitoAttivazione

        delega = crea_delega(
            delegante=delegante,
            ruolo=ruolo_delegante,
            email_delegato="nuovo@example.com",
            data_fine=DOMANI,
        )
        assert delega.delegato.stato == "IN_ATTESA"
        assert not delega.delegato.has_usable_password()
        invito = InvitoAttivazione.objects.get(email="nuovo@example.com")
        assert invito.delega_pendente_id == delega.id

    def test_scadenza_oltre_quella_del_ruolo_e_un_errore(self, gruppo):
        u = _persona("cg@campania.agesci.it")
        ruolo = Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo, data_fine=DOMANI)
        with pytest.raises(ValidationError):
            crea_delega(
                delegante=u,
                ruolo=ruolo,
                email_delegato="d@campania.agesci.it",
                data_fine=FRA_UN_ANNO,
            )

    def test_quarta_delega_attiva_sullo_stesso_ruolo_e_un_errore(self, delegante, ruolo_delegante):
        for i in range(3):
            crea_delega(
                delegante=delegante,
                ruolo=ruolo_delegante,
                email_delegato=f"d{i}@campania.agesci.it",
                data_fine=DOMANI,
            )
        with pytest.raises(ValidationError):
            crea_delega(
                delegante=delegante,
                ruolo=ruolo_delegante,
                email_delegato="quarto@campania.agesci.it",
                data_fine=DOMANI,
            )

    def test_delega_di_secondo_livello_e_un_errore_strutturale(self, delegante, ruolo_delegante):
        """Un delegato non può a sua volta ri-delegare (D-04): il ruolo che
        detiene solo per delega non ha `ruolo.utente == delegato`."""
        delegato = _persona("delegato@campania.agesci.it")
        crea_delega(
            delegante=delegante,
            ruolo=ruolo_delegante,
            email_delegato=delegato.email,
            data_fine=DOMANI,
        )
        with pytest.raises(ValidationError):
            crea_delega(
                delegante=delegato,
                ruolo=ruolo_delegante,
                email_delegato="terzo@campania.agesci.it",
                data_fine=DOMANI,
            )


class TestRevoca:
    def test_revoca_esplicita_disattiva_la_delega(self, delegante, ruolo_delegante):
        delegato = _persona("delegato@campania.agesci.it")
        delega = crea_delega(
            delegante=delegante,
            ruolo=ruolo_delegante,
            email_delegato=delegato.email,
            data_fine=DOMANI,
        )
        revoca_delega(delega, revocata_da=delegante)
        delega.refresh_from_db()
        assert delega.attiva is False
        assert ruoli_effettivi(delegato) == []

    def test_revoca_del_ruolo_di_origine_fa_cascata_su_tutte_le_deleghe(
        self, delegante, ruolo_delegante
    ):
        delegati = [_persona(f"d{i}@campania.agesci.it") for i in range(2)]
        for d in delegati:
            crea_delega(
                delegante=delegante,
                ruolo=ruolo_delegante,
                email_delegato=d.email,
                data_fine=DOMANI,
            )
        ruolo_delegante.attivo = False
        ruolo_delegante.save(update_fields=["attivo"])
        conteggio = revoca_deleghe_di_ruolo(ruolo_delegante)

        assert conteggio == 2
        for d in delegati:
            assert Delega.objects.get(delegato=d).attiva is False
