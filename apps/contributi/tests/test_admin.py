"""Regressione: un ModelAdmin senza readonly_fields sullo stato crasherebbe
al primo salvataggio (FSMField protected=True + ModelForm._post_clean(), che
ri-assegna ogni campo del form)."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite

from apps.anagrafica.models import Capo, CensimentoCapo
from apps.contributi.admin import CampagnaAdmin, PartecipazioneAdmin
from apps.contributi.models import Campagna, Partecipazione, TipologiaCampo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _crea_via_admin_form(model_admin, instance, dati_form):
    form_class = model_admin.get_form(request=None, obj=instance)
    form = form_class(data=dati_form, instance=instance)
    assert form.is_valid(), form.errors
    form.save()


class TestCampagnaAdminNonCrasha:
    def test_modifica_campagna_da_admin(self):
        campagna = Campagna.objects.create(
            anno=ANNO,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2025, 10, 1),
            data_fine_inserimento=datetime.date(2026, 9, 30),
        )
        model_admin = CampagnaAdmin(Campagna, AdminSite())

        _crea_via_admin_form(
            model_admin,
            campagna,
            {
                "anno": ANNO,
                "budget": "1200.00",
                "tetto_per_partecipazione": "50.00",
                "data_inizio_inserimento": "2025-10-01",
                "data_fine_inserimento": "2026-09-30",
                "riferimento_bonifico": "",
            },
        )

        campagna.refresh_from_db()
        assert campagna.budget == Decimal("1200.00")


class TestPartecipazioneAdminNonCrasha:
    def test_modifica_partecipazione_da_admin(self):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO, gruppo=gruppo)
        campagna = Campagna.objects.create(
            anno=ANNO,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2025, 10, 1),
            data_fine_inserimento=datetime.date(2026, 9, 30),
        )
        tipologia = TipologiaCampo.objects.get(codice="CFM")
        partecipazione = Partecipazione(
            campagna=campagna,
            capo=capo,
            gruppo=gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base scout",
            quota_versata=Decimal("51.50"),
        )
        partecipazione.full_clean(exclude=["stato"])
        partecipazione.save()

        model_admin = PartecipazioneAdmin(Partecipazione, AdminSite())

        _crea_via_admin_form(
            model_admin,
            partecipazione,
            {
                "campagna": campagna.pk,
                "capo": capo.pk,
                "gruppo": gruppo.pk,
                "tipologia": tipologia.pk,
                "descrizione_altro": "",
                "data_inizio": "2026-06-01",
                "data_fine": "2026-06-08",
                "luogo": "Base scout modificata",
                "quota_versata": "51.50",
                "motivazione_respingimento": "",
            },
        )

        partecipazione.refresh_from_db()
        assert partecipazione.luogo == "Base scout modificata"
