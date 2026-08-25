"""M4 del piano di sviluppo: "Visualizza anagrafica" come hub a tre schede
(Esporta / Cerca capo / Registro esportazioni), perimetro allargato
all'unione dei tre permessi ma ogni scheda condizionata al proprio."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return _con_mfa_configurata(utente)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def admin() -> Utente:
    utente = _persona("admin@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.ADMIN)
    return _con_mfa_configurata(utente)


class TestPerimetroCG:
    """CG ha RUOLI_EXPORT_ANAGRAFICA ma non RUOLI_RICERCA_CAPO né
    RUOLI_VISUALIZZAZIONE_ESPORTAZIONI: caso reale (non ipotetico) di
    disallineamento fra i tre permessi."""

    def test_cg_accede_alla_pagina_e_vede_solo_la_scheda_esporta(self, client, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get("/anagrafica/export/")

        assert response.status_code == 200
        assert response.context["puo_esportare"] is True
        assert response.context["puo_cercare_capo"] is False
        assert response.context["puo_vedere_registro"] is False
        assert "form" in response.context

    def test_cg_non_accede_a_ricerca_capo(self, client, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get("/anagrafica/incarichi/ricerca-capo/")
        assert response.status_code == 403

    def test_cg_non_accede_al_registro(self, client, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get("/anagrafica/export/registro/")
        assert response.status_code == 403


class TestPerimetroSegreteria:
    def test_segreteria_vede_esporta_e_cerca_capo_non_registro(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/export/")

        assert response.status_code == 200
        assert response.context["puo_esportare"] is True
        assert response.context["puo_cercare_capo"] is True
        assert response.context["puo_vedere_registro"] is False


class TestPerimetroAdmin:
    def test_admin_vede_le_tre_schede(self, client, admin):
        client.force_login(admin)
        response = client.get("/anagrafica/export/")

        assert response.status_code == 200
        assert response.context["puo_esportare"] is True
        assert response.context["puo_cercare_capo"] is True
        assert response.context["puo_vedere_registro"] is True

        response = client.get("/anagrafica/incarichi/ricerca-capo/")
        assert response.status_code == 200

        response = client.get("/anagrafica/export/registro/")
        assert response.status_code == 200
