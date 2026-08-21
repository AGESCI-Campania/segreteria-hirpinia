import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.allowlist import crea_voce_allowlist, elimina_voce_allowlist
from apps.organizzazione.models import AllowlistGruppo, Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


class TestCreaVoceAllowlist:
    def test_permesso_negato(self, gruppo):
        estraneo = _persona("estraneo@campania.agesci.it")
        with pytest.raises(PermissionDenied):
            crea_voce_allowlist(utente=estraneo, codice_gruppo=gruppo.codice, email="a@x.it")

    def test_gruppo_inesistente(self, segreteria):
        with pytest.raises(ValidationError):
            crea_voce_allowlist(utente=segreteria, codice_gruppo="E9999", email="a@x.it")

    def test_email_duplicata(self, segreteria, gruppo):
        crea_voce_allowlist(utente=segreteria, codice_gruppo=gruppo.codice, email="a@x.it")
        with pytest.raises(ValidationError):
            crea_voce_allowlist(utente=segreteria, codice_gruppo=gruppo.codice, email="a@x.it")

    def test_creazione_riuscita(self, segreteria, gruppo):
        voce = crea_voce_allowlist(utente=segreteria, codice_gruppo=gruppo.codice, email="a@x.it")
        assert voce.creata_da == segreteria


class TestEliminaVoceAllowlist:
    def test_permesso_negato(self, gruppo):
        estraneo = _persona("estraneo@campania.agesci.it")
        voce = AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")
        with pytest.raises(PermissionDenied):
            elimina_voce_allowlist(utente=estraneo, voce=voce)
        assert AllowlistGruppo.objects.filter(pk=voce.pk).exists()

    def test_eliminazione_riuscita(self, segreteria, gruppo):
        voce = AllowlistGruppo.objects.create(codice_gruppo=gruppo.codice, email="a@x.it")
        elimina_voce_allowlist(utente=segreteria, voce=voce)
        assert not AllowlistGruppo.objects.filter(pk=voce.pk).exists()


def test_risolvi_case_insensitive():
    AllowlistGruppo.objects.create(codice_gruppo="E0133", email="Avellino1@Campania.Agesci.It")
    voce = AllowlistGruppo.risolvi("avellino1@campania.agesci.it")
    assert voce is not None
    assert voce.codice_gruppo == "E0133"


def test_risolvi_nessun_match():
    assert AllowlistGruppo.risolvi("inesistente@campania.agesci.it") is None


def test_unicita_email():
    AllowlistGruppo.objects.create(codice_gruppo="E0133", email="avellino1@campania.agesci.it")
    with pytest.raises(IntegrityError), transaction.atomic():
        AllowlistGruppo.objects.create(codice_gruppo="E0134", email="avellino1@campania.agesci.it")
