"""Test dell'endpoint di autocompletamento per "Inserisci partecipazione"
(M14): terzo endpoint di ricerca soci, distinto sia da
cerca_capo_per_codice_socio (D-34, solo match esatto) sia da
RicercaSociAutocompleteView (M7, cross-gruppo per decisione presa lì) — qui
il perimetro è quello di risolvi_gruppo_competente (D-21/D-34): un CG vede
solo il proprio gruppo, SEGRETERIA/ADMIN/RDZ tutta la zona."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.contributi.models import Campagna
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
def e9001() -> Gruppo:
    return Gruppo.objects.get(codice="E9001")


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


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


def _capo(codice_socio, nome, cognome, gruppo, anno_scout=ANNO) -> Capo:
    c = Capo.objects.create(codice_socio=codice_socio, nome=nome, cognome=cognome)
    CensimentoCapo.objects.create(capo=c, anno_scout=anno_scout, gruppo=gruppo)
    return c


class TestPartecipazioniRicercaSociAutocomplete:
    def _url(self, campagna) -> str:
        return f"/contributi/campagne/{campagna.pk}/partecipazioni/ricerca-soci-autocomplete/"

    def test_richiede_autenticazione(self, client, campagna):
        response = client.get(self._url(campagna), {"q": "Rossi"})
        assert response.status_code in (302, 403)

    def test_meno_di_due_caratteri_nessun_risultato(self, client, segreteria, campagna):
        client.force_login(segreteria)
        response = client.get(self._url(campagna), {"q": "r"})
        assert response.json() == {"risultati": []}

    def test_cg_trova_solo_i_censiti_nel_proprio_gruppo(
        self, client, cg_gruppo, gruppo, altro_gruppo, campagna
    ):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        _capo("10002", "LUCA", "ROSSI", altro_gruppo)
        client.force_login(cg_gruppo)

        response = client.get(self._url(campagna), {"q": "Rossi"})

        dati = response.json()["risultati"]
        assert len(dati) == 1
        assert dati[0] == {
            "codice_socio": "10001",
            "nome": "MARIO",
            "cognome": "ROSSI",
            "gruppo": "AVELLINO 1",
        }

    def test_segreteria_trova_censiti_in_tutta_la_zona(
        self, client, segreteria, gruppo, altro_gruppo, campagna
    ):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        _capo("10002", "LUCA", "ROSSI", altro_gruppo)
        client.force_login(segreteria)

        response = client.get(self._url(campagna), {"q": "Rossi"})

        assert len(response.json()["risultati"]) == 2

    def test_censito_in_e9001_escluso_per_segreteria(self, client, segreteria, e9001, campagna):
        _capo("30003", "ANNA", "VERDI", e9001)
        client.force_login(segreteria)

        response = client.get(self._url(campagna), {"q": "Verdi"})

        assert response.json()["risultati"] == []

    def test_cerca_per_codice_socio(self, client, segreteria, gruppo, campagna):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        client.force_login(segreteria)

        response = client.get(self._url(campagna), {"q": "10001"})

        assert len(response.json()["risultati"]) == 1

    def test_risposta_non_contiene_dati_riservati(self, client, segreteria, gruppo, campagna):
        _capo("10001", "MARIO", "ROSSI", gruppo)
        client.force_login(segreteria)

        response = client.get(self._url(campagna), {"q": "Rossi"})

        assert set(response.json()["risultati"][0].keys()) == {
            "codice_socio",
            "nome",
            "cognome",
            "gruppo",
        }

    def test_risultati_limitati(self, client, segreteria, gruppo, campagna):
        for i in range(20):
            _capo(f"1000{i}", "MARIO", f"ROSSI{i}", gruppo)
        client.force_login(segreteria)

        response = client.get(self._url(campagna), {"q": "Rossi"})

        assert len(response.json()["risultati"]) <= 15

    def test_nessuna_query_nessun_risultato(self, client, segreteria, campagna):
        client.force_login(segreteria)
        response = client.get(self._url(campagna))
        assert response.json() == {"risultati": []}
