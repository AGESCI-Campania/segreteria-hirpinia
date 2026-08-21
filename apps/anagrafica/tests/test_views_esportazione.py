"""Test delle viste di export anagrafica (M8, D-23): perimetro, formati,
tracciamento."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    EsportazioneAnagrafica,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


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
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


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


@pytest.fixture
def utente_senza_ruolo() -> Utente:
    return _con_mfa_configurata(_persona("senza-ruolo@campania.agesci.it"))


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    IncaricoUnita.objects.create(
        capo=c,
        anno_scout=ANNO,
        gruppo_servizio=gruppo,
        codice_unita="H1",
        nome_unita="BRANCO",
        branca=BrancaUnita.LC,
        genere_unita="MISTO",
        funzione=FunzioneIncarico.CAPO_UNITA,
        origine=OrigineIncarico.IMPORT,
    )
    return c


class TestPerimetro:
    def test_accesso_negato_senza_ruolo(self, client, utente_senza_ruolo):
        client.force_login(utente_senza_ruolo)
        response = client.get("/anagrafica/export/")
        assert response.status_code == 403

    def test_accesso_negato_anonimo(self, client):
        response = client.get("/anagrafica/export/")
        assert response.status_code in (302, 403)

    def test_cg_puo_accedere(self, client, cg_gruppo):
        client.force_login(cg_gruppo)
        response = client.get("/anagrafica/export/")
        assert response.status_code == 200

    def test_cg_non_puo_esportare_gruppo_fuori_perimetro(
        self, client, cg_gruppo, altro_gruppo, capo
    ):
        client.force_login(cg_gruppo)
        response = client.post(
            "/anagrafica/export/",
            {
                "anno_scout": ANNO,
                "gruppo": altro_gruppo.codice,
                "unita": "",
                "funzione": "",
                "stato": "ATTIVI",
                "raggruppamento": "NESSUNO",
                "profilo_colonne": "MINIMO",
                "formato": "csv",
            },
        )
        assert response.status_code == 200
        assert not response.get("Content-Disposition")
        assert EsportazioneAnagrafica.objects.count() == 0


class TestRicercaTabella:
    def _filtri(self, **override):
        filtri = {
            "anno_scout": ANNO,
            "gruppo": "",
            "unita": "",
            "funzione": "",
            "stato": "ATTIVI",
            "raggruppamento": "NESSUNO",
            "profilo_colonne": "MINIMO",
        }
        filtri.update(override)
        return filtri

    def test_senza_filtri_non_mostra_tabella(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/export/")

        assert response.status_code == 200
        assert "righe_tabella" not in response.context

    def test_con_filtri_mostra_tabella_senza_scaricare_nulla(
        self, client, segreteria, capo, gruppo
    ):
        client.force_login(segreteria)
        response = client.get("/anagrafica/export/", self._filtri())

        assert response.status_code == 200
        assert not response.get("Content-Disposition")
        assert response.context["numero_capi"] == 1
        assert len(response.context["righe_tabella"]) == 1
        assert EsportazioneAnagrafica.objects.count() == 0

    def test_cg_non_puo_cercare_gruppo_fuori_perimetro(self, client, cg_gruppo, altro_gruppo, capo):
        client.force_login(cg_gruppo)
        response = client.get("/anagrafica/export/", self._filtri(gruppo=altro_gruppo.codice))

        assert response.status_code == 200
        assert "righe_tabella" not in response.context
        assert response.context["form"].errors


class TestGenerazioneFile:
    def _dati(self, **override):
        dati = {
            "anno_scout": ANNO,
            "gruppo": "",
            "unita": "",
            "funzione": "",
            "stato": "ATTIVI",
            "raggruppamento": "NESSUNO",
            "profilo_colonne": "MINIMO",
            "formato": "csv",
        }
        dati.update(override)
        return dati

    def test_csv_con_bom_e_punto_e_virgola(self, client, segreteria, capo, gruppo):
        client.force_login(segreteria)
        response = client.post("/anagrafica/export/", self._dati())

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        contenuto = b"".join(response.streaming_content) if response.streaming else response.content
        assert contenuto.startswith(b"\xef\xbb\xbf")
        assert b";" in contenuto

    def test_xlsx_generato(self, client, segreteria, capo, gruppo):
        client.force_login(segreteria)
        response = client.post("/anagrafica/export/", self._dati(formato="xlsx"))

        assert response.status_code == 200
        assert (
            response["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def test_esportazione_registrata(self, client, segreteria, capo, gruppo):
        client.force_login(segreteria)
        client.post("/anagrafica/export/", self._dati())

        esportazione = EsportazioneAnagrafica.objects.get()
        assert esportazione.utente == segreteria
        assert esportazione.anno_scout == ANNO
        assert esportazione.numero_capi == 1
        assert esportazione.numero_righe == 1
        assert esportazione.profilo_colonne == "MINIMO"


class TestRegistroEsportazioni:
    def test_visibile_solo_ad_admin(self, client, admin, segreteria):
        client.force_login(segreteria)
        response = client.get("/anagrafica/export/registro/")
        assert response.status_code == 403

        client.force_login(admin)
        response = client.get("/anagrafica/export/registro/")
        assert response.status_code == 200
