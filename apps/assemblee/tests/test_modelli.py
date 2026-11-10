"""Modelli del modulo Assemblee (D-70)."""

import datetime

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.assemblee.models import (
    Assemblea,
    AventeDiritto,
    OrigineAvente,
    Provenienza,
    Seduta,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E2913", nome="ARIANO 1")


@pytest.fixture
def assemblea() -> Assemblea:
    return Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)


def _avente(assemblea, gruppo, **kwargs) -> AventeDiritto:
    kwargs.setdefault("nome", "Mario")
    kwargs.setdefault("cognome", "Rossi")
    kwargs.setdefault("origine", OrigineAvente.IMPORT)
    return AventeDiritto.objects.create(assemblea=assemblea, gruppo=gruppo, **kwargs)


class TestAssemblea:
    def test_autunnale_usa_i_censiti_dell_anno_precedente(self, assemblea):
        assert assemblea.anno_censimento == 2026

    def test_primaverile_usa_i_censiti_dell_anno_corrente(self):
        primaverile = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        assert primaverile.anno_censimento == 2027

    def test_nome_con_anno_associativo(self, assemblea):
        assert str(assemblea) == "Assemblea autunnale 2026/2027"

    def test_conclusa(self, assemblea):
        assert not assemblea.conclusa
        assemblea.conclusa_il = timezone.now()
        assert assemblea.conclusa


class TestSeduta:
    def test_una_sola_seduta_per_convocazione(self, assemblea):
        oggi = datetime.date(2026, 11, 22)
        Seduta.objects.create(assemblea=assemblea, convocazione=1, data=oggi)
        with pytest.raises(IntegrityError), transaction.atomic():
            Seduta.objects.create(assemblea=assemblea, convocazione=1, data=oggi)


class TestAventeDiritto:
    def test_codice_socio_unico_nella_stessa_assemblea(self, assemblea, gruppo):
        _avente(assemblea, gruppo, codice_socio="123456")
        with pytest.raises(IntegrityError), transaction.atomic():
            _avente(assemblea, gruppo, codice_socio="123456", nome="Altro")

    def test_piu_capi_senza_codice_socio(self, assemblea, gruppo):
        """I capi da precensire non hanno codice socio: il vincolo di unicità
        non deve scattare fra loro."""
        _avente(assemblea, gruppo, origine=OrigineAvente.MANUALE, provenienza=Provenienza.NON_NOTA)
        _avente(
            assemblea,
            gruppo,
            nome="Anna",
            origine=OrigineAvente.MANUALE,
            provenienza=Provenienza.RIENTRO,
        )
        assert assemblea.aventi_diritto.count() == 2

    def test_inserito_a_mano_richiede_la_provenienza(self, assemblea, gruppo):
        with pytest.raises(IntegrityError), transaction.atomic():
            _avente(assemblea, gruppo, origine=OrigineAvente.MANUALE)

    def test_importato_senza_provenienza(self, assemblea, gruppo):
        assert _avente(assemblea, gruppo).provenienza == ""

    def test_nell_elenco_esclude_gli_eliminati(self, assemblea, gruppo):
        resta = _avente(assemblea, gruppo, codice_socio="1")
        _avente(assemblea, gruppo, codice_socio="2", eliminato_il=timezone.now())
        assert list(assemblea.aventi_diritto.nell_elenco()) == [resta]

    def test_trasferito(self, assemblea, gruppo, altro_gruppo):
        rimasto = _avente(assemblea, gruppo, codice_socio="1", gruppo_origine=gruppo)
        trasferito = _avente(assemblea, altro_gruppo, codice_socio="2", gruppo_origine=gruppo)
        nuovo = _avente(
            assemblea, gruppo, origine=OrigineAvente.MANUALE, provenienza=Provenienza.NON_NOTA
        )
        assert not rimasto.trasferito
        assert trasferito.trasferito
        assert not nuovo.trasferito
