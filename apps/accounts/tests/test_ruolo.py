import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def utente_dominio_ammesso():
    return Utente.objects.create(
        username="cg", email="cg@campania.agesci.it", tipo=TipoUtente.PERSONA
    )


@pytest.fixture
def utente_dominio_non_ammesso():
    return Utente.objects.create(
        username="esterno", email="esterno@gmail.com", tipo=TipoUtente.PERSONA
    )


class TestDominioEmail:
    def test_dominio_non_ammesso_e_un_errore(self, utente_dominio_non_ammesso):
        ruolo = Ruolo(utente=utente_dominio_non_ammesso, tipo=Ruolo.Tipo.RDZ)
        with pytest.raises(ValidationError):
            ruolo.clean()

    def test_dominio_ammesso_e_valido(self, utente_dominio_ammesso):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.RDZ)
        ruolo.clean()  # non deve sollevare

    def test_admin_esente_dal_vincolo_di_dominio(self, utente_dominio_non_ammesso):
        ruolo = Ruolo(utente=utente_dominio_non_ammesso, tipo=Ruolo.Tipo.ADMIN)
        ruolo.clean()  # non deve sollevare: ADMIN è l'unica eccezione a D-04


class TestCoerenzaCampi:
    def test_cg_senza_gruppo_e_un_errore(self, utente_dominio_ammesso):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.CG)
        with pytest.raises(ValidationError):
            ruolo.clean()

    def test_cg_con_gruppo_e_valido(self, utente_dominio_ammesso, gruppo):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        ruolo.clean()

    def test_iabz_senza_branca_e_un_errore(self, utente_dominio_ammesso):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.IABZ)
        with pytest.raises(ValidationError):
            ruolo.clean()

    def test_iabz_con_branca_e_valido(self, utente_dominio_ammesso):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.IABZ, branca=Ruolo.Branca.LC)
        ruolo.clean()

    def test_isz_senza_settore_e_un_errore(self, utente_dominio_ammesso):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.ISZ)
        with pytest.raises(ValidationError):
            ruolo.clean()

    def test_rdz_con_gruppo_valorizzato_e_un_errore(self, utente_dominio_ammesso, gruppo):
        ruolo = Ruolo(utente=utente_dominio_ammesso, tipo=Ruolo.Tipo.RDZ, gruppo=gruppo)
        with pytest.raises(ValidationError):
            ruolo.clean()
