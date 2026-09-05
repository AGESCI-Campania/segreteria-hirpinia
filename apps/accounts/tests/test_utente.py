import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


def _utente(**kwargs):
    defaults = {"username": "u", "email": "u@example.com"}
    defaults.update(kwargs)
    return Utente(**defaults)


class TestClean:
    def test_persona_con_gruppo_e_un_errore(self, gruppo):
        u = _utente(tipo=TipoUtente.PERSONA, gruppo=gruppo)
        with pytest.raises(ValidationError):
            u.clean()

    def test_gruppo_senza_gruppo_e_un_errore(self):
        u = _utente(tipo=TipoUtente.GRUPPO)
        with pytest.raises(ValidationError):
            u.clean()

    def test_gruppo_con_codice_socio_e_un_errore(self, gruppo):
        u = _utente(tipo=TipoUtente.GRUPPO, gruppo=gruppo, codice_socio="12345")
        with pytest.raises(ValidationError):
            u.clean()

    def test_persona_valida(self):
        u = _utente(tipo=TipoUtente.PERSONA, codice_socio="12345")
        u.clean()  # non deve sollevare

    def test_gruppo_valido(self, gruppo):
        u = _utente(tipo=TipoUtente.GRUPPO, gruppo=gruppo)
        u.clean()  # non deve sollevare


class TestCreateSuperuser:
    def test_crea_anche_il_ruolo_admin(self):
        utente = Utente.objects.create_superuser(
            username="admin", email="admin@example.com", password="password123!"
        )

        assert Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.ADMIN, attivo=True).exists()

    def test_nasce_attivo_senza_invito(self):
        utente = Utente.objects.create_superuser(
            username="admin2", email="admin2@example.com", password="password123!"
        )

        assert utente.stato == StatoUtente.ATTIVO


class TestAccountConsentiti:
    def test_secondo_account_oltre_il_limite_e_un_errore(self, gruppo):
        Utente.objects.create(
            username="a", email="a@example.com", tipo=TipoUtente.GRUPPO, gruppo=gruppo
        )
        secondo = _utente(
            username="b", email="b@example.com", tipo=TipoUtente.GRUPPO, gruppo=gruppo
        )
        with pytest.raises(ValidationError):
            secondo.clean()

    def test_secondo_account_su_e9001_e_consentito(self):
        e9001 = Gruppo.objects.get(codice="E9001")  # seminato da 0002_seed_e9001
        Utente.objects.create(
            username="rzm",
            email="rzm.zonahirpinia@campania.agesci.it",
            tipo=TipoUtente.GRUPPO,
            gruppo=e9001,
        )
        secondo = _utente(
            username="rzf",
            email="rzf.zonahirpinia@campania.agesci.it",
            tipo=TipoUtente.GRUPPO,
            gruppo=e9001,
        )
        secondo.clean()  # non deve sollevare, account_consentiti=2
