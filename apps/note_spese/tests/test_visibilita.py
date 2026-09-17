"""D-65/D-66: perimetro di visibilità delle note spese."""

import datetime

import pytest

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import Evento, NotaSpese
from apps.note_spese.visibilita import note_visibili
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, codice_socio: str | None = None) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, codice_socio=codice_socio
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def capo_a() -> Capo:
    return Capo.objects.create(codice_socio="111111A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_b() -> Capo:
    return Capo.objects.create(codice_socio="222222B", nome="Luigi", cognome="Bianchi")


@pytest.fixture
def utente_capo_a(capo_a: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo_a.pk)


@pytest.fixture
def utente_senza_capo() -> Utente:
    return _persona("account.gruppo@example.it")


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def capogruppo(capo_a: Capo) -> Utente:
    """D-65: nessun privilegio, verificato esplicitamente perché è il caso
    più facile da confondere con `gruppi_visibili()` usato altrove."""
    utente = _persona("capogruppo@example.it", codice_socio=capo_a.pk)
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo_id="E0133")
    return utente


@pytest.fixture
def nota_a(gruppo, capo_a, evento) -> NotaSpese:
    return NotaSpese.objects.create(
        beneficiario=capo_a, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )


@pytest.fixture
def nota_b(gruppo, capo_b, evento) -> NotaSpese:
    return NotaSpese.objects.create(
        beneficiario=capo_b, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )


class TestNoteVisibili:
    def test_capo_vede_solo_le_proprie(self, utente_capo_a, nota_a, nota_b) -> None:
        visibili = list(note_visibili(utente_capo_a))
        assert visibili == [nota_a]

    def test_segreteria_vede_tutte(self, segreteria, nota_a, nota_b) -> None:
        visibili = set(note_visibili(segreteria))
        assert visibili == {nota_a, nota_b}

    def test_capogruppo_non_ha_privilegi(self, capogruppo, nota_a, nota_b) -> None:
        visibili = list(note_visibili(capogruppo))
        assert visibili == [nota_a]

    def test_account_senza_capo_non_vede_nulla(self, utente_senza_capo, nota_a, nota_b) -> None:
        assert list(note_visibili(utente_senza_capo)) == []

    def test_nota_eliminata_non_e_visibile_al_beneficiario(self, utente_capo_a, nota_a) -> None:
        nota_a.eliminata_il = datetime.datetime.now(datetime.UTC)
        nota_a.save(update_fields=["eliminata_il"])
        assert list(note_visibili(utente_capo_a)) == []

    def test_nota_eliminata_non_e_visibile_alla_segreteria(self, segreteria, nota_a) -> None:
        nota_a.eliminata_il = datetime.datetime.now(datetime.UTC)
        nota_a.save(update_fields=["eliminata_il"])
        assert list(note_visibili(segreteria)) == []
