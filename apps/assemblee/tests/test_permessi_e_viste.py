"""Permessi, viste e voce di menu del modulo Assemblee (D-70)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.utils import timezone

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.assemblee.models import Assemblea, OperatoreVoto, Seduta, TipoAssemblea
from apps.assemblee.permessi import (
    accede_assemblee,
    assemblee_visibili,
    puo_gestire_assemblee,
    puo_operare,
)
from apps.core.menu import sezioni_menu

pytestmark = pytest.mark.django_db


def _persona(email: str, ruolo: str | None = None) -> Utente:
    n = Utente.objects.count()
    utente = Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
        # ADMIN/SEGRETERIA/RdZ devono avere l'MFA, altrimenti il middleware
        # li manda alla configurazione prima di qualsiasi pagina.
        Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    return _persona("segreteria@campania.agesci.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def capo() -> Utente:
    return _persona("capo@example.it")


@pytest.fixture
def assemblea() -> Assemblea:
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    return assemblea


def _voci_moduli(utente) -> list[str]:
    for sezione in sezioni_menu(utente):
        if sezione.etichetta == "Moduli":
            return [v.etichetta for v in sezione.voci]
    return []


class TestPermessi:
    @pytest.mark.parametrize("tipo", [Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ])
    def test_gestori(self, tipo):
        utente = _persona(f"{tipo}@example.it", tipo)
        assert puo_gestire_assemblee(utente)
        assert accede_assemblee(utente)

    def test_capogruppo_non_gestisce(self, capo):
        Ruolo.objects.create(utente=capo, tipo=Ruolo.Tipo.CG)
        assert not puo_gestire_assemblee(capo)
        assert not accede_assemblee(capo)

    def test_operatore_vede_solo_la_sua_assemblea_non_conclusa(self, capo, assemblea):
        altra = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        OperatoreVoto.objects.create(assemblea=assemblea, utente=capo)
        assert list(assemblee_visibili(capo)) == [assemblea]
        assert puo_operare(capo, assemblea)
        assert not puo_operare(capo, altra)
        assert not puo_gestire_assemblee(capo)

        assemblea.conclusa_il = timezone.now()
        assemblea.save()
        assert not accede_assemblee(capo)


class TestMenu:
    def test_voce_per_i_gestori(self, segreteria):
        assert "Assemblee" in _voci_moduli(segreteria)

    def test_nessuna_voce_per_un_capo(self, capo):
        assert "Assemblee" not in _voci_moduli(capo)

    def test_voce_per_l_operatore(self, capo, assemblea):
        OperatoreVoto.objects.create(assemblea=assemblea, utente=capo)
        assert "Assemblee" in _voci_moduli(capo)


class TestViste:
    def test_un_capo_non_accede(self, client, capo):
        client.force_login(capo)
        assert client.get("/assemblee/").status_code == 403

    def test_crea_assemblea_con_prima_convocazione(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post(
            "/assemblee/nuova/",
            {
                "tipo": TipoAssemblea.AUTUNNALE,
                "anno_scout": 2027,
                "sessione": "ORDINARIA",
                "data_convocazione": "2026-11-22",
                "ora_convocazione": "09:30",
                "luogo": "Avellino",
            },
        )
        assemblea = Assemblea.objects.get()
        assert response.status_code == 302
        assert assemblea.creata_da == segreteria
        seduta = assemblea.sedute.get()
        assert seduta.convocazione == Seduta.Convocazione.PRIMA
        assert seduta.data == datetime.date(2026, 11, 22)
        assert seduta.luogo == "Avellino"

    def test_un_operatore_non_crea_assemblee(self, client, capo, assemblea):
        OperatoreVoto.objects.create(assemblea=assemblea, utente=capo)
        client.force_login(capo)
        assert client.get("/assemblee/nuova/").status_code == 403

    def test_dettaglio_per_operatore_e_404_per_altre(self, client, capo, assemblea):
        altra = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        OperatoreVoto.objects.create(assemblea=assemblea, utente=capo)
        client.force_login(capo)
        assert client.get(f"/assemblee/{assemblea.pk}/").status_code == 200
        assert client.get(f"/assemblee/{altra.pk}/").status_code == 404

    def test_un_operatore_non_nomina_altri_operatori(self, client, capo, assemblea):
        OperatoreVoto.objects.create(assemblea=assemblea, utente=capo)
        client.force_login(capo)
        response = client.post(f"/assemblee/{assemblea.pk}/comitato/aggiungi/", {"avente": 1})
        assert response.status_code == 403
        assert OperatoreVoto.objects.filter(assemblea=assemblea).count() == 1

    def test_assemblea_conclusa_non_accetta_nuovi_operatori(self, client, segreteria, capo):
        conclusa = Assemblea.objects.create(
            tipo=TipoAssemblea.AUTUNNALE, anno_scout=2026, conclusa_il=timezone.now()
        )
        client.force_login(segreteria)
        response = client.post(f"/assemblee/{conclusa.pk}/comitato/aggiungi/", {"avente": 1})
        assert response.status_code == 403
