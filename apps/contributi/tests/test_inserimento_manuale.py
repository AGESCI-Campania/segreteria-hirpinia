"""Inserimento manuale di una partecipazione (§7 passo 2, D-34, A-8)."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.contributi.inserimento import inserisci_partecipazione_manuale
from apps.contributi.models import Campagna, TipologiaCampo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str) -> Utente:
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def e9001() -> Gruppo:
    # Già seminato da organizzazione/migrations/0002_seed_e9001.py.
    return Gruppo.objects.get(codice="E9001")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


@pytest.fixture
def tipologia() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    u = _persona("cg-avellino1@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return u


@pytest.fixture
def cg_altro_gruppo(altro_gruppo) -> Utente:
    u = _persona("cg-avellino2@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=altro_gruppo)
    return u


@pytest.fixture
def segreteria() -> Utente:
    u = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
    return u


def _inserisci(
    *, utente, campagna, codice_socio="10001", tipologia, quota_versata=None, **override
):
    dati = {
        "utente": utente,
        "campagna": campagna,
        "codice_socio": codice_socio,
        "tipologia": tipologia,
        "data_inizio": datetime.date(2026, 6, 1),
        "data_fine": datetime.date(2026, 6, 8),
        "luogo": "Base scout",
        "quota_versata": quota_versata,
    }
    dati.update(override)
    return inserisci_partecipazione_manuale(**dati)


class TestInserimentoManuale:
    def test_cg_inserisce_per_il_proprio_gruppo(self, capo, campagna, tipologia, cg_gruppo, gruppo):
        partecipazione = _inserisci(utente=cg_gruppo, campagna=campagna, tipologia=tipologia)
        assert partecipazione.gruppo_id == gruppo.codice
        assert partecipazione.quota_versata == Decimal("51.50")  # precompilata da quota_default

    def test_cg_non_inserisce_per_capo_censito_altrove(
        self, capo, campagna, tipologia, cg_altro_gruppo
    ):
        with pytest.raises(PermissionDenied):
            _inserisci(utente=cg_altro_gruppo, campagna=campagna, tipologia=tipologia)

    def test_segreteria_inserisce_su_qualunque_gruppo(self, capo, campagna, tipologia, segreteria):
        partecipazione = _inserisci(utente=segreteria, campagna=campagna, tipologia=tipologia)
        assert partecipazione.pk is not None

    def test_capo_censito_in_e9001_escluso(self, campagna, tipologia, segreteria, e9001):
        capo_e9001 = Capo.objects.create(codice_socio="20002", nome="LUCA", cognome="BIANCHI")
        CensimentoCapo.objects.create(capo=capo_e9001, anno_scout=ANNO, gruppo=e9001)
        with pytest.raises(ValidationError):
            _inserisci(
                utente=segreteria, campagna=campagna, codice_socio="20002", tipologia=tipologia
            )

    def test_campagna_non_aperta_rifiutata(self, capo, campagna, tipologia, segreteria):
        # .update() bypassa il descriptor FSM (query SQL diretta); si rilegge
        # un'istanza NUOVA, così la prima assegnazione di `stato` su
        # quell'oggetto è consentita anche con protected=True.
        Campagna.objects.filter(pk=campagna.pk).update(stato="IN_VALUTAZIONE")
        campagna_aggiornata = Campagna.objects.get(pk=campagna.pk)
        with pytest.raises(ValidationError):
            _inserisci(utente=segreteria, campagna=campagna_aggiornata, tipologia=tipologia)

    def test_campagna_fuori_finestra_rifiutata(self, capo, tipologia, segreteria):
        campagna_passata = Campagna.objects.create(
            anno=2020,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2019, 10, 1),
            data_fine_inserimento=datetime.date(2019, 12, 31),
        )
        with pytest.raises(ValidationError):
            _inserisci(utente=segreteria, campagna=campagna_passata, tipologia=tipologia)

    def test_quota_versata_esplicita_non_sovrascritta(self, capo, campagna, tipologia, segreteria):
        partecipazione = _inserisci(
            utente=segreteria,
            campagna=campagna,
            tipologia=tipologia,
            quota_versata=Decimal("30.00"),
        )
        assert partecipazione.quota_versata == Decimal("30.00")

    def test_tipologia_senza_quota_default_e_nessuna_quota_e_errore(
        self, capo, campagna, segreteria
    ):
        tipologia_senza_default = TipologiaCampo.objects.create(
            codice="ALTRO1", nome="Altro campo", livello="ALTRO"
        )
        with pytest.raises(ValidationError):
            _inserisci(utente=segreteria, campagna=campagna, tipologia=tipologia_senza_default)

    def test_capo_non_censito_nellanno_rifiutato(self, campagna, tipologia, segreteria):
        Capo.objects.create(codice_socio="30003", nome="ANNA", cognome="VERDI")
        with pytest.raises(ValidationError):
            _inserisci(
                utente=segreteria, campagna=campagna, codice_socio="30003", tipologia=tipologia
            )

    def test_tipologia_altro_senza_descrizione_rifiutata(self, capo, campagna, segreteria):
        tipologia_altro = TipologiaCampo.objects.get(codice="ALTRO")
        with pytest.raises(ValidationError):
            _inserisci(
                utente=segreteria,
                campagna=campagna,
                tipologia=tipologia_altro,
                quota_versata=Decimal("30.00"),
            )

    def test_tipologia_altro_con_descrizione_salvata(self, capo, campagna, segreteria):
        tipologia_altro = TipologiaCampo.objects.get(codice="ALTRO")
        partecipazione = _inserisci(
            utente=segreteria,
            campagna=campagna,
            tipologia=tipologia_altro,
            quota_versata=Decimal("30.00"),
            descrizione_altro="Campo di specialità",
        )
        assert partecipazione.descrizione_altro == "Campo di specialità"
