"""D-52: fasce tariffarie e tariffa vigente alla data della spesa."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.note_spese.calcolo_km import fascia_per, tariffa_km
from apps.note_spese.models import TariffaChilometrica

pytestmark = pytest.mark.django_db


class TestFasciaPer:
    def test_tre_o_piu_passeggeri_e_sempre_la_fascia_alta(self) -> None:
        assert fascia_per(3, Decimal("10")) == "TRE_O_PIU"
        assert fascia_per(5, Decimal("500")) == "TRE_O_PIU"

    def test_uno_o_due_passeggeri_fino_a_200_km_e_breve(self) -> None:
        assert fascia_per(1, Decimal("200")) == "BREVE"
        assert fascia_per(2, Decimal("199.9")) == "BREVE"

    def test_uno_o_due_passeggeri_oltre_200_km_e_lunga(self) -> None:
        assert fascia_per(1, Decimal("200.1")) == "LUNGA"
        assert fascia_per(2, Decimal("500")) == "LUNGA"

    def test_zero_passeggeri_e_come_uno_o_due(self) -> None:
        assert fascia_per(0, Decimal("50")) == "BREVE"


class TestTariffaKm:
    def test_tariffa_vigente_alla_data(self) -> None:
        TariffaChilometrica.objects.create(
            fascia="BREVE",
            importo_km=Decimal("0.20"),
            valida_dal=datetime.date(2026, 1, 1),
        )
        assert tariffa_km("BREVE", datetime.date(2027, 6, 1)) == Decimal("0.20")

    def test_tariffa_precedente_non_si_applica_dopo_il_cambio(self) -> None:
        TariffaChilometrica.objects.create(
            fascia="BREVE",
            importo_km=Decimal("0.20"),
            valida_dal=datetime.date(2020, 1, 1),
            valida_al=datetime.date(2025, 12, 31),
        )
        TariffaChilometrica.objects.create(
            fascia="BREVE",
            importo_km=Decimal("0.22"),
            valida_dal=datetime.date(2026, 1, 1),
        )
        assert tariffa_km("BREVE", datetime.date(2024, 6, 1)) == Decimal("0.20")
        assert tariffa_km("BREVE", datetime.date(2027, 1, 1)) == Decimal("0.22")

    def test_nessuna_tariffa_configurata_solleva_errore(self) -> None:
        with pytest.raises(ValidationError):
            tariffa_km("LUNGA", datetime.date(2027, 1, 1))


class TestTariffaChilometricaModello:
    def test_periodi_sovrapposti_stessa_fascia_non_validi(self) -> None:
        TariffaChilometrica.objects.create(
            fascia="BREVE",
            importo_km=Decimal("0.20"),
            valida_dal=datetime.date(2026, 1, 1),
        )
        sovrapposta = TariffaChilometrica(
            fascia="BREVE",
            importo_km=Decimal("0.22"),
            valida_dal=datetime.date(2026, 6, 1),
        )
        with pytest.raises(ValidationError):
            sovrapposta.clean()

    def test_periodi_consecutivi_stessa_fascia_validi(self) -> None:
        TariffaChilometrica.objects.create(
            fascia="BREVE",
            importo_km=Decimal("0.20"),
            valida_dal=datetime.date(2020, 1, 1),
            valida_al=datetime.date(2025, 12, 31),
        )
        successiva = TariffaChilometrica(
            fascia="BREVE",
            importo_km=Decimal("0.22"),
            valida_dal=datetime.date(2026, 1, 1),
        )
        successiva.clean()

    def test_fasce_diverse_possono_sovrapporsi(self) -> None:
        TariffaChilometrica.objects.create(
            fascia="BREVE",
            importo_km=Decimal("0.20"),
            valida_dal=datetime.date(2026, 1, 1),
        )
        altra_fascia = TariffaChilometrica(
            fascia="LUNGA",
            importo_km=Decimal("0.15"),
            valida_dal=datetime.date(2026, 1, 1),
        )
        altra_fascia.clean()

    def test_valida_al_precedente_a_valida_dal_non_valido(self) -> None:
        tariffa = TariffaChilometrica(
            fascia="BREVE",
            importo_km=Decimal("0.20"),
            valida_dal=datetime.date(2026, 6, 1),
            valida_al=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            tariffa.clean()
