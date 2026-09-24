"""Issue #17 (descrizione_altro visibile nella tabella partecipazioni) e #18
parte 2 (motivazione_respingimento visibile per le partecipazioni respinte),
stesso file/stessa tabella toccati insieme (`campagna_dettaglio.html`)."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.models import Campagna, Partecipazione, StatoPartecipazione, TipologiaCampo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026
IBAN_VALIDO = "IT60X0542811101000000123456"


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1", iban=IBAN_VALIDO)


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


def _capo(n: int) -> Capo:
    return Capo.objects.create(codice_socio=f"1{n:04d}", nome="MARIO", cognome=f"ROSSI{n}")


class TestDescrizioneAltroVisibile:
    def test_descrizione_altro_mostrata_in_tabella(self, client, segreteria, campagna, gruppo):
        tipologia = TipologiaCampo.objects.get(codice="ALTRO")
        Partecipazione.objects.create(
            campagna=campagna,
            capo=_capo(0),
            gruppo=gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            quota_versata=Decimal("10.00"),
            descrizione_altro="Campo di specialità volontariato",
            stato=StatoPartecipazione.INSERITA,
        )
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna.pk}/")
        assert "Campo di specialità volontariato" in response.content.decode()

    def test_nessuna_descrizione_nessun_rigo_extra(self, client, segreteria, campagna, gruppo):
        tipologia = TipologiaCampo.objects.get(codice="CFM")
        Partecipazione.objects.create(
            campagna=campagna,
            capo=_capo(0),
            gruppo=gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            quota_versata=Decimal("10.00"),
            stato=StatoPartecipazione.INSERITA,
        )
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna.pk}/")
        assert response.status_code == 200


class TestMotivazioneRespingimentoVisibile:
    def test_motivazione_mostrata_per_partecipazione_respinta(
        self, client, segreteria, campagna, gruppo
    ):
        tipologia = TipologiaCampo.objects.get(codice="CFM")
        Partecipazione.objects.create(
            campagna=campagna,
            capo=_capo(0),
            gruppo=gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            quota_versata=Decimal("10.00"),
            stato=StatoPartecipazione.RESPINTA,
            motivazione_respingimento="Documentazione mancante",
        )
        client.force_login(segreteria)
        response = client.get(f"/contributi/campagne/{campagna.pk}/")
        assert "Documentazione mancante" in response.content.decode()
