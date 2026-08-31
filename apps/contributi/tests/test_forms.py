"""Form di inserimento manuale partecipazione (M16/M17)."""

import datetime
from decimal import Decimal

import pytest

from apps.contributi.forms import PartecipazioneManualeForm
from apps.contributi.models import TipologiaCampo

pytestmark = pytest.mark.django_db


def _dati(**override) -> dict:
    dati = {
        "codice_socio": "10001",
        "tipologia": TipologiaCampo.objects.get(codice="CFM").pk,
        "data_inizio": datetime.date(2026, 6, 1),
        "data_fine": datetime.date(2026, 6, 8),
        "luogo": "Base scout",
        "quota_versata": "51.50",
        "note": "",
    }
    dati.update(override)
    return dati


class TestPartecipazioneManualeForm:
    def test_quota_versata_obbligatoria(self):
        form = PartecipazioneManualeForm(data=_dati(quota_versata=""))
        assert not form.is_valid()
        assert "quota_versata" in form.errors

    def test_quota_versata_valida_accettata(self):
        form = PartecipazioneManualeForm(data=_dati())
        assert form.is_valid(), form.errors
        assert form.cleaned_data["quota_versata"] == Decimal("51.50")

    def test_luogo_vuoto_accettato(self):
        form = PartecipazioneManualeForm(data=_dati(luogo=""))
        assert form.is_valid(), form.errors

    def test_note_vuota_accettata(self):
        form = PartecipazioneManualeForm(data=_dati(note=""))
        assert form.is_valid(), form.errors

    def test_note_valorizzata_accettata(self):
        form = PartecipazioneManualeForm(data=_dati(note="Nota libera."))
        assert form.is_valid(), form.errors
        assert form.cleaned_data["note"] == "Nota libera."
