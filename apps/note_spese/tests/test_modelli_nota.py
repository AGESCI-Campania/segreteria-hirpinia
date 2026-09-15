"""Test F2: testata/righe della nota (D-44/D-45), evento (D-49), passeggero
(D-53/D-57). Niente transizioni FSM con effetti di dominio qui: sono F3."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.anagrafica.models import Capo
from apps.note_spese.models import (
    CategoriaSpesa,
    Evento,
    NotaSpese,
    RigaSpesa,
    RigaSpesaPasseggero,
    StatoNota,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

IBAN_IT_VALIDO = "IT60X0542811101000000123456"


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


class TestEvento:
    def test_data_fine_precedente_a_inizio_non_valida(self) -> None:
        evento = Evento(
            nome="Test",
            data_inizio=datetime.date(2027, 7, 10),
            data_fine=datetime.date(2027, 7, 1),
        )
        with pytest.raises(ValidationError):
            evento.full_clean()

    def test_creato_non_validato_di_default(self, evento: Evento) -> None:
        assert evento.validato is False


class TestNotaSpese:
    def test_stato_di_default_bozza(self, gruppo: Gruppo, capo: Capo, evento: Evento) -> None:
        nota = NotaSpese.objects.create(beneficiario=capo, gruppo_censimento=gruppo, evento=evento)
        assert nota.stato == StatoNota.BOZZA
        # FSMField(protected=True) ha rotto refresh_from_db() altrove nel
        # progetto (M4/M5) senza FSMModelMixin: verifica che qui funzioni.
        nota.refresh_from_db()
        assert nota.stato == StatoNota.BOZZA

    def test_anno_contabilizzazione_nullo_alla_creazione(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        # Trappola D-41 esplicitamente richiamata dai requisiti.
        nota = NotaSpese.objects.create(beneficiario=capo, gruppo_censimento=gruppo, evento=evento)
        assert nota.anno_contabilizzazione is None

    def test_incarico_altro_obbligatorio_se_incarico_assente(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        nota = NotaSpese(beneficiario=capo, gruppo_censimento=gruppo, evento=evento)
        with pytest.raises(ValidationError) as errore:
            nota.clean()
        assert "incarico_altro" in errore.value.message_dict

    def test_incarico_altro_valorizzato_supera_la_validazione(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        nota = NotaSpese(
            beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
        )
        nota.clean()  # non deve sollevare

    def test_compilatore_uguale_beneficiario_non_valido(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        nota = NotaSpese(
            beneficiario=capo,
            compilatore=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
        )
        with pytest.raises(ValidationError) as errore:
            nota.clean()
        assert "compilatore" in errore.value.message_dict

    def test_iban_non_valido_segnalato(self, gruppo: Gruppo, capo: Capo, evento: Evento) -> None:
        nota = NotaSpese(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            iban="IT00INVALIDO",
        )
        with pytest.raises(ValidationError) as errore:
            nota.clean()
        assert "iban" in errore.value.message_dict

    def test_iban_valido_supera_la_validazione(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        nota = NotaSpese(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            iban=IBAN_IT_VALIDO,
        )
        nota.clean()  # non deve sollevare

    def test_numero_nullo_alla_creazione(self, gruppo: Gruppo, capo: Capo, evento: Evento) -> None:
        # Assegnato dalla transizione BOZZA->INVIATA (F3), non qui.
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
        )
        assert nota.numero is None


class TestRigaSpesaEPasseggero:
    def test_riga_collegata_alla_nota(self, gruppo: Gruppo, capo: Capo, evento: Evento) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
        )
        categoria = CategoriaSpesa.objects.create(nome="Vitto test")
        riga = RigaSpesa.objects.create(
            nota=nota,
            categoria=categoria,
            data=datetime.date(2027, 7, 2),
            importo=Decimal("20.00"),
        )
        assert nota.righe.get() == riga

    def test_passeggero_richiede_capo_o_nome_libero(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Autista"
        )
        categoria = CategoriaSpesa.objects.create(
            nome="Auto test", tipo_calcolo="CHILOMETRICO", richiede_tratta=True
        )
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2)
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                RigaSpesaPasseggero.objects.create(riga=riga)

    def test_passeggero_con_nome_libero_consentito(
        self, gruppo: Gruppo, capo: Capo, evento: Evento
    ) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Autista"
        )
        categoria = CategoriaSpesa.objects.create(
            nome="Auto test 2", tipo_calcolo="CHILOMETRICO", richiede_tratta=True
        )
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2)
        )
        passeggero = RigaSpesaPasseggero.objects.create(riga=riga, nome_libero="Ospite esterno")
        assert passeggero.capo is None
