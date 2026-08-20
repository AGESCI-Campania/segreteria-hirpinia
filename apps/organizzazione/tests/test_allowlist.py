import pytest
from django.db import IntegrityError, transaction

from apps.organizzazione.models import AllowlistGruppo

pytestmark = pytest.mark.django_db


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
