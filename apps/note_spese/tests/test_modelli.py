"""Test minimi F1 (piano approvato in docs/ignored/PLAN-nota-spese.md): alberi
multi-livello, PROTECT su cancellazione di un nodo con figli, unicità del
budget per centro di costo e anno, idempotenza delle data migration."""

import importlib
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.note_spese.models import BudgetCentroCosto, CategoriaSpesa, CentroCosto, Localita

pytestmark = pytest.mark.django_db


class TestAlberoCategoriaSpesa:
    def test_albero_multi_livello(self) -> None:
        viaggio = CategoriaSpesa.objects.create(nome="Viaggio radice test")
        auto = CategoriaSpesa.objects.create(nome="Auto test", parent=viaggio)
        assert auto.parent == viaggio
        assert viaggio.figli.get() == auto

    def test_protect_su_cancellazione_nodo_con_figli(self) -> None:
        viaggio = CategoriaSpesa.objects.create(nome="Viaggio radice test 2")
        CategoriaSpesa.objects.create(nome="Auto test 2", parent=viaggio)
        with pytest.raises(ProtectedError):
            viaggio.delete()


class TestAlberoCentroCosto:
    def test_albero_multi_livello(self) -> None:
        zona = CentroCosto.objects.create(nome="Zona test")
        gruppo = CentroCosto.objects.create(nome="Gruppo test", parent=zona)
        assert gruppo.parent == zona
        assert zona.figli.get() == gruppo

    def test_protect_su_cancellazione_nodo_con_figli(self) -> None:
        zona = CentroCosto.objects.create(nome="Zona test 2")
        CentroCosto.objects.create(nome="Gruppo test 2", parent=zona)
        with pytest.raises(ProtectedError):
            zona.delete()


class TestBudgetCentroCosto:
    def test_unicita_per_centro_e_anno(self) -> None:
        centro = CentroCosto.objects.create(nome="Centro budget test")
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2026, importo=Decimal("100.00")
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BudgetCentroCosto.objects.create(
                    centro_costo=centro, anno_scout=2026, importo=Decimal("50.00")
                )

    def test_stesso_centro_anni_diversi_consentito(self) -> None:
        centro = CentroCosto.objects.create(nome="Centro budget test 2")
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2026, importo=Decimal("100.00")
        )
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2027, importo=Decimal("120.00")
        )
        assert centro.budget_annuali.count() == 2

    def test_sforamento_figlio_non_persiste_sul_padre(self) -> None:
        # D-47: il budget è per nodo, senza vincolo di capienza aggregata
        # persistito: creare/aggiornare il budget di un figlio non tocca
        # in alcun modo quello del padre.
        padre = CentroCosto.objects.create(nome="Padre budget test")
        figlio = CentroCosto.objects.create(nome="Figlio budget test", parent=padre)
        BudgetCentroCosto.objects.create(
            centro_costo=padre, anno_scout=2026, importo=Decimal("100.00")
        )
        BudgetCentroCosto.objects.create(
            centro_costo=figlio, anno_scout=2026, importo=Decimal("9999.00")
        )
        padre.refresh_from_db()
        budget_padre = padre.budget_annuali.get(anno_scout=2026)
        assert budget_padre.importo == Decimal("100.00")


class TestMigrazioniDati:
    def test_categorie_iniziali_idempotenti(self) -> None:
        m = importlib.import_module("apps.note_spese.migrations.0002_categorie_iniziali")
        conteggio_prima = CategoriaSpesa.objects.count()
        m.crea_categorie(apps, None)
        m.crea_categorie(apps, None)
        assert CategoriaSpesa.objects.count() == conteggio_prima

    def test_localita_comuni_idempotenti(self) -> None:
        m = importlib.import_module("apps.note_spese.migrations.0003_localita_comuni")
        conteggio_prima = Localita.objects.count()
        m.crea_localita(apps, None)
        m.crea_localita(apps, None)
        assert Localita.objects.count() == conteggio_prima

    def test_localita_comuni_contiene_avellino(self) -> None:
        avellino = Localita.objects.get(codice_istat="064008")
        assert avellino.nome == "Avellino"
        assert avellino.estero is False
        assert avellino.latitudine == Decimal("40.913637")
