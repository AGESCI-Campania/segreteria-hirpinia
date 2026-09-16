"""Capienza dei centri di costo (D-47/D-48): consumo solo alla liquidazione,
nessuna cascata padre/figli."""

import datetime
from decimal import Decimal

import pytest

from apps.anagrafica.models import Capo
from apps.note_spese.budget import capienza_centro_costo
from apps.note_spese.models import (
    BudgetCentroCosto,
    CategoriaSpesa,
    CentroCosto,
    Evento,
    NotaSpese,
    RigaSpesa,
    StatoNota,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test")


def _nota_liquidata(
    gruppo: Gruppo,
    capo: Capo,
    evento: Evento,
    categoria: CategoriaSpesa,
    centro_costo: CentroCosto,
    importo: Decimal,
    anno_contabilizzazione: int,
) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        centro_costo=centro_costo,
        stato=StatoNota.LIQUIDATA,
        anno_contabilizzazione=anno_contabilizzazione,
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=importo
    )
    return nota


class TestCapienzaCentroCosto:
    def test_senza_budget_e_senza_note_capienza_zero(self):
        centro = CentroCosto.objects.create(nome="Zona")
        capienza = capienza_centro_costo(centro, 2027)
        assert capienza.budget == Decimal("0")
        assert capienza.consumato == Decimal("0")
        assert capienza.residuo == Decimal("0")

    def test_consumato_somma_solo_note_liquidate_dello_stesso_anno(
        self, gruppo, capo, evento, categoria
    ):
        centro = CentroCosto.objects.create(nome="Zona")
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2027, importo=Decimal("100")
        )
        _nota_liquidata(gruppo, capo, evento, categoria, centro, Decimal("30"), 2027)
        _nota_liquidata(gruppo, capo, evento, categoria, centro, Decimal("40"), 2028)

        capienza = capienza_centro_costo(centro, 2027)

        assert capienza.consumato == Decimal("30")
        assert capienza.residuo == Decimal("70")

    def test_note_non_liquidate_non_consumano(self, gruppo, capo, evento, categoria):
        centro = CentroCosto.objects.create(nome="Zona")
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2027, importo=Decimal("100")
        )
        nota = NotaSpese.objects.create(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            centro_costo=centro,
            stato=StatoNota.APPROVATA,
        )
        RigaSpesa.objects.create(
            nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("999")
        )

        capienza = capienza_centro_costo(centro, 2027)

        assert capienza.consumato == Decimal("0")

    def test_sforamento_del_figlio_non_intacca_il_padre(self, gruppo, capo, evento, categoria):
        padre = CentroCosto.objects.create(nome="Zona")
        figlio = CentroCosto.objects.create(nome="Campo estivo", parent=padre)
        BudgetCentroCosto.objects.create(centro_costo=padre, anno_scout=2027, importo=Decimal("50"))
        BudgetCentroCosto.objects.create(
            centro_costo=figlio, anno_scout=2027, importo=Decimal("10")
        )
        _nota_liquidata(gruppo, capo, evento, categoria, figlio, Decimal("30"), 2027)

        capienza_padre = capienza_centro_costo(padre, 2027)
        capienza_figlio = capienza_centro_costo(figlio, 2027)

        assert capienza_padre.consumato == Decimal("0")
        assert capienza_padre.residuo == Decimal("50")
        assert capienza_figlio.consumato == Decimal("30")
        assert capienza_figlio.residuo == Decimal("-20")
