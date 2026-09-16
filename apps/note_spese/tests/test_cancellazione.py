"""D-60/D-61: cancellazione delle note."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.cancellazione import elimina_nota_reale, elimina_nota_soft
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese, RigaSpesa, StatoNota
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
def capo() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def altro_capo_utente() -> Utente:
    return _persona("altro@example.it", codice_socio="999999Z")


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def nota(gruppo, capo, evento) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )
    categoria = CategoriaSpesa.objects.create(nome="Vitto test cancellazione")
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


class TestEliminaNotaSoft:
    def test_beneficiario_puo_eliminare_la_propria_nota(self, nota, capo_utente) -> None:
        elimina_nota_soft(nota, capo_utente)
        nota.refresh_from_db()
        assert nota.eliminata_il is not None

    def test_segreteria_puo_eliminare_qualsiasi_nota(self, nota, segreteria) -> None:
        elimina_nota_soft(nota, segreteria)
        nota.refresh_from_db()
        assert nota.eliminata_il is not None

    def test_un_altro_capo_non_puo_eliminare(self, nota, altro_capo_utente) -> None:
        with pytest.raises(PermissionDenied):
            elimina_nota_soft(nota, altro_capo_utente)

    def test_nota_liquidata_non_e_mai_cancellabile(
        self, gruppo, capo, evento, capo_utente, segreteria
    ) -> None:
        nota_liquidata = NotaSpese.objects.create(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            stato=StatoNota.LIQUIDATA,
        )
        with pytest.raises(ValidationError):
            elimina_nota_soft(nota_liquidata, capo_utente)
        with pytest.raises(ValidationError):
            elimina_nota_soft(nota_liquidata, segreteria)


class TestEliminaNotaReale:
    def test_segreteria_puo_cancellare_realmente(self, nota, segreteria) -> None:
        pk = nota.pk
        elimina_nota_reale(nota, segreteria)
        assert not NotaSpese.objects.filter(pk=pk).exists()

    def test_beneficiario_non_puo_cancellare_realmente(self, nota, capo_utente) -> None:
        with pytest.raises(PermissionDenied):
            elimina_nota_reale(nota, capo_utente)
        assert NotaSpese.objects.filter(pk=nota.pk).exists()

    def test_nota_liquidata_non_e_mai_cancellabile(self, gruppo, capo, evento, segreteria) -> None:
        nota_liquidata = NotaSpese.objects.create(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            stato=StatoNota.LIQUIDATA,
        )
        with pytest.raises(ValidationError):
            elimina_nota_reale(nota_liquidata, segreteria)
        assert NotaSpese.objects.filter(pk=nota_liquidata.pk).exists()
