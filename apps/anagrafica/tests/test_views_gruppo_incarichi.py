"""Test della subview incarichi del gruppo (M5.4, D-35): vive in
apps.anagrafica per non violare la direzione delle dipendenze fra app."""

import datetime

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.organizzazione.models import Gruppo, anno_scout_corrente

pytestmark = pytest.mark.django_db

ANNO = anno_scout_corrente()


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


def _incarico(gruppo, *, codice_socio, cessato_il=None) -> IncaricoUnita:
    capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=ANNO,
        gruppo_servizio=gruppo,
        codice_unita="H1",
        nome_unita="BRANCO",
        branca=BrancaUnita.LC,
        genere_unita="MISTO",
        funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
        origine=OrigineIncarico.MANUALE,
        cessato_il=cessato_il,
    )


class TestGruppoIncarichiView:
    def test_cg_vede_gli_incarichi_del_proprio_gruppo(self, client, cg_gruppo, gruppo):
        _incarico(gruppo, codice_socio="10001")
        client.force_login(cg_gruppo)

        response = client.get(f"/anagrafica/gruppi/{gruppo.codice}/incarichi/")

        assert response.status_code == 200
        assert len(response.context["incarichi"]) == 1

    def test_cg_non_accede_a_un_altro_gruppo(self, client, cg_gruppo):
        altro = Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")
        client.force_login(cg_gruppo)

        response = client.get(f"/anagrafica/gruppi/{altro.codice}/incarichi/")

        assert response.status_code == 403

    def test_solo_attivi_di_default(self, client, segreteria, gruppo):
        _incarico(gruppo, codice_socio="10001")
        _incarico(
            gruppo,
            codice_socio="10002",
            cessato_il=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        client.force_login(segreteria)

        response = client.get(f"/anagrafica/gruppi/{gruppo.codice}/incarichi/")

        assert len(response.context["incarichi"]) == 1

    def test_storico_mostra_anche_i_cessati(self, client, segreteria, gruppo):
        _incarico(gruppo, codice_socio="10001")
        _incarico(
            gruppo,
            codice_socio="10002",
            cessato_il=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        client.force_login(segreteria)

        response = client.get(f"/anagrafica/gruppi/{gruppo.codice}/incarichi/?storico=1")

        assert len(response.context["incarichi"]) == 2

    def test_breadcrumb_pagina_figlia(self, client, segreteria, gruppo):
        client.force_login(segreteria)

        response = client.get(f"/anagrafica/gruppi/{gruppo.codice}/incarichi/")

        items = response.context["breadcrumb_items"]
        assert items[-3] == {"label": "Gruppi"}
        assert items[-2] == {"label": gruppo.nome}
        assert items[-1] == {"label": "Incarichi"}

    def test_pulsante_assegna_incarico_porta_il_gruppo_in_query(self, client, segreteria, gruppo):
        client.force_login(segreteria)

        response = client.get(f"/anagrafica/gruppi/{gruppo.codice}/incarichi/")

        assert f"/anagrafica/incarichi/assegna/?gruppo={gruppo.codice}" in response.content.decode()


class TestAssegnaIncaricoViewDefaultGruppo:
    """M6: 'Assegna incarico' non è più una voce di menu di primo livello, si
    raggiunge da qui con il gruppo precompilato."""

    def test_gruppo_in_query_precompila_il_form(self, client, segreteria, gruppo):
        client.force_login(segreteria)

        response = client.get(f"/anagrafica/incarichi/assegna/?gruppo={gruppo.codice}")

        assert response.status_code == 200
        assert response.context["form"].initial["gruppo_servizio"] == gruppo.codice

    def test_resta_possibile_scegliere_un_gruppo_diverso(self, client, segreteria, gruppo):
        altro = Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")
        capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        from apps.anagrafica.models import CensimentoCapo

        CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO, gruppo=gruppo)
        client.force_login(segreteria)

        response = client.post(
            "/anagrafica/incarichi/assegna/",
            {
                "codice_socio": "10001",
                "anno_scout": ANNO,
                "gruppo_servizio": altro.codice,
                "codice_unita": "H1",
                "nome_unita": "BRANCO",
                "branca": BrancaUnita.LC,
                "genere_unita": "MISTO",
                "funzione": FunzioneIncarico.AIUTO_CAPO_UNITA,
            },
        )

        assert response.status_code == 302
        assert IncaricoUnita.objects.filter(gruppo_servizio=altro, capo=capo).exists()

    def test_senza_gruppo_in_query_nessun_default(self, client, segreteria):
        client.force_login(segreteria)

        response = client.get("/anagrafica/incarichi/assegna/")

        assert "gruppo_servizio" not in response.context["form"].initial

    def test_post_capo_unita_senza_branca_e_un_errore(self, client, segreteria, gruppo):
        capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        from apps.anagrafica.models import CensimentoCapo

        CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO, gruppo=gruppo)
        client.force_login(segreteria)

        response = client.post(
            "/anagrafica/incarichi/assegna/",
            {
                "codice_socio": "10001",
                "anno_scout": ANNO,
                "gruppo_servizio": gruppo.codice,
                "codice_unita": "H1",
                "nome_unita": "BRANCO",
                "branca": "",
                "genere_unita": "MISTO",
                "funzione": FunzioneIncarico.CAPO_UNITA,
            },
        )

        assert response.status_code == 200
        assert not IncaricoUnita.objects.filter(capo=capo).exists()

    def test_post_funzione_senza_branca_obbligatoria_ok(self, client, segreteria, gruppo):
        capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        from apps.anagrafica.models import CensimentoCapo

        CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO, gruppo=gruppo)
        client.force_login(segreteria)

        response = client.post(
            "/anagrafica/incarichi/assegna/",
            {
                "codice_socio": "10001",
                "anno_scout": ANNO,
                "gruppo_servizio": gruppo.codice,
                "codice_unita": "G1",
                "nome_unita": "COMUNITA CAPI",
                "branca": "",
                "genere_unita": "MISTO",
                "funzione": FunzioneIncarico.SUPPORTO_GRUPPO,
            },
        )

        assert response.status_code == 302
        incarico = IncaricoUnita.objects.get(capo=capo)
        assert incarico.branca == BrancaUnita.SCONOSCIUTA
