"""Test dell'endpoint di autocompletamento per l'assegnazione incarico (M7).

Esplicitamente distinto da RicercaCapoView/cerca_capo_per_codice_socio (D-34):
qui la ricerca copre tutti i gruppi e ammette nome/cognome, non solo il
codice socio esatto."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
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


def _capo(codice_socio, nome, cognome, gruppo) -> Capo:
    c = Capo.objects.create(codice_socio=codice_socio, nome=nome, cognome=cognome)
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


class TestRicercaSociAutocomplete:
    URL = "/anagrafica/incarichi/ricerca-soci-autocomplete/"

    def test_richiede_autenticazione(self, client):
        response = client.get(self.URL, {"q": "Rossi"})
        assert response.status_code in (302, 403)

    def test_meno_di_due_caratteri_nessun_risultato(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get(self.URL, {"q": "r"})
        assert response.json() == {"risultati": []}

    def test_cerca_per_cognome(self, client, segreteria, gruppo):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        client.force_login(segreteria)

        response = client.get(self.URL, {"q": "Rossi"})

        dati = response.json()["risultati"]
        assert len(dati) == 1
        assert dati[0] == {
            "codice_socio": "10001",
            "nome": "MARIO",
            "cognome": "ROSSI",
            "gruppo": "AVELLINO 1",
            "gruppo_codice": "E0133",
        }

    def test_cerca_per_codice_socio(self, client, segreteria, gruppo):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        client.force_login(segreteria)

        response = client.get(self.URL, {"q": "10001"})

        assert len(response.json()["risultati"]) == 1

    def test_cerca_per_nome_gruppo(self, client, segreteria, gruppo):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        client.force_login(segreteria)

        response = client.get(self.URL, {"q": "AVELLINO 1"})

        assert len(response.json()["risultati"]) == 1

    def test_cg_trova_capi_censiti_in_un_altro_gruppo(self, client, cg_gruppo, altro_gruppo):
        """Deviazione dichiarata da D-34: qui la ricerca copre tutti i
        gruppi, non solo gruppi_visibili."""
        _capo("10002", "LUCA", "VERDI", altro_gruppo)
        client.force_login(cg_gruppo)

        response = client.get(self.URL, {"q": "Verdi"})

        assert len(response.json()["risultati"]) == 1

    def test_risposta_non_contiene_dati_riservati(self, client, segreteria, gruppo):
        """Solo identità minima + gruppo di censimento (D-34): mai recapiti
        né altri campi anagrafici. `gruppo_codice` serve al client per
        precompilare il gruppo di servizio, non è un dato riservato."""
        _capo("10001", "MARIO", "ROSSI", gruppo)
        client.force_login(segreteria)

        response = client.get(self.URL, {"q": "Rossi"})

        assert set(response.json()["risultati"][0].keys()) == {
            "codice_socio",
            "nome",
            "cognome",
            "gruppo",
            "gruppo_codice",
        }

    def test_risultati_limitati(self, client, segreteria, gruppo):
        for i in range(20):
            _capo(f"1000{i}", "MARIO", f"ROSSI{i}", gruppo)
        client.force_login(segreteria)

        response = client.get(self.URL, {"q": "Rossi"})

        assert len(response.json()["risultati"]) <= 15

    def test_nessuna_query_nessun_risultato(self, client, segreteria):
        client.force_login(segreteria)
        response = client.get(self.URL)
        assert response.json() == {"risultati": []}
