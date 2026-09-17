"""F6c: creazione della nota e delle righe documentali."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.note_spese.anno_associativo import anno_associativo_per_data
from apps.note_spese.creazione import aggiungi_riga_documentale, crea_nota_bozza
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese, StatoNota, TipoCalcolo
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO_CORRENTE = anno_associativo_per_data(timezone.now().date())


def _persona(email: str, codice_socio: str | None = None) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, codice_socio=codice_socio
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo(gruppo) -> Capo:
    capo = Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")
    CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO_CORRENTE, gruppo=gruppo)
    return capo


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def capo_non_censito() -> Capo:
    return Capo.objects.create(codice_socio="999999Z", nome="Luigi", cognome="Bianchi")


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def segreteria_capo(gruppo) -> Utente:
    """Segreteria che è a sua volta un capo censito, per verificare che
    compaia come `compilatore` (D-36)."""
    capo_segreteria = Capo.objects.create(codice_socio="777777S", nome="Anna", cognome="Verdi")
    CensimentoCapo.objects.create(capo=capo_segreteria, anno_scout=ANNO_CORRENTE, gruppo=gruppo)
    utente = _persona("segreteria2@campania.agesci.it", codice_socio=capo_segreteria.pk)
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def incarico(capo, gruppo) -> IncaricoUnita:
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=ANNO_CORRENTE,
        gruppo_servizio=gruppo,
        codice_unita="R1",
        branca=BrancaUnita.RS,
        funzione=FunzioneIncarico.CAPO_UNITA,
        origine=OrigineIncarico.MANUALE,
    )


@pytest.fixture
def categoria_documentale() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test creazione")


class TestCreaNotaBozza:
    def test_capo_crea_la_propria_nota(self, capo, capo_utente, evento, incarico) -> None:
        nota = crea_nota_bozza(
            utente=capo_utente,
            beneficiario=capo,
            evento=evento,
            incarico=incarico,
            incarico_altro="",
        )
        assert nota.stato == StatoNota.BOZZA
        assert nota.beneficiario_id == capo.pk
        assert nota.compilatore_id is None
        assert nota.gruppo_censimento.codice == "E0133"

    def test_capo_non_censito_blocca_la_creazione(self, capo_non_censito, evento) -> None:
        utente = _persona("luigi@example.it", codice_socio=capo_non_censito.pk)
        with pytest.raises(ValidationError):
            crea_nota_bozza(
                utente=utente,
                beneficiario=capo_non_censito,
                evento=evento,
                incarico=None,
                incarico_altro="Cuoco",
            )

    def test_serve_incarico_o_testo_libero(self, capo, capo_utente, evento) -> None:
        with pytest.raises(ValidationError):
            crea_nota_bozza(
                utente=capo_utente,
                beneficiario=capo,
                evento=evento,
                incarico=None,
                incarico_altro="",
            )

    def test_capo_non_puo_creare_per_un_altro(self, capo, evento) -> None:
        altro = _persona("altro@example.it", codice_socio="555555X")
        with pytest.raises(PermissionDenied):
            crea_nota_bozza(
                utente=altro,
                beneficiario=capo,
                evento=evento,
                incarico=None,
                incarico_altro="Cuoco",
            )

    def test_segreteria_crea_per_conto_terzi_senza_compilatore_se_account_funzionale(
        self, capo, segreteria, evento
    ) -> None:
        nota = crea_nota_bozza(
            utente=segreteria,
            beneficiario=capo,
            evento=evento,
            incarico=None,
            incarico_altro="Cuoco",
        )
        assert nota.beneficiario_id == capo.pk
        assert nota.compilatore_id is None
        assert nota.creata_da_id == segreteria.pk

    def test_segreteria_capo_compare_come_compilatore(self, capo, segreteria_capo, evento) -> None:
        nota = crea_nota_bozza(
            utente=segreteria_capo,
            beneficiario=capo,
            evento=evento,
            incarico=None,
            incarico_altro="Cuoco",
        )
        assert nota.compilatore_id == segreteria_capo.codice_socio

    def test_incarico_di_un_altro_capo_e_rifiutato(self, capo, capo_utente, evento, gruppo) -> None:
        altro_capo = Capo.objects.create(codice_socio="888888B", nome="Carlo", cognome="Neri")
        incarico_altrui = IncaricoUnita.objects.create(
            capo=altro_capo,
            anno_scout=ANNO_CORRENTE,
            gruppo_servizio=gruppo,
            codice_unita="R2",
            branca=BrancaUnita.RS,
            funzione=FunzioneIncarico.CAPO_UNITA,
            origine=OrigineIncarico.MANUALE,
        )
        with pytest.raises(ValidationError):
            crea_nota_bozza(
                utente=capo_utente,
                beneficiario=capo,
                evento=evento,
                incarico=incarico_altrui,
                incarico_altro="",
            )

    def test_iban_non_valido_e_rifiutato(self, capo, capo_utente, evento, incarico) -> None:
        with pytest.raises(ValidationError):
            crea_nota_bozza(
                utente=capo_utente,
                beneficiario=capo,
                evento=evento,
                incarico=incarico,
                incarico_altro="",
                iban="IT00INVALIDO",
            )


class TestAggiungiRigaDocumentale:
    @pytest.fixture
    def nota(self, capo, capo_utente, evento, incarico) -> NotaSpese:
        return crea_nota_bozza(
            utente=capo_utente,
            beneficiario=capo,
            evento=evento,
            incarico=incarico,
            incarico_altro="",
        )

    def test_beneficiario_aggiunge_una_riga(self, nota, capo_utente, categoria_documentale) -> None:
        riga = aggiungi_riga_documentale(
            nota=nota,
            utente=capo_utente,
            categoria=categoria_documentale,
            data=datetime.date(2027, 7, 2),
            importo=Decimal("15.50"),
        )
        assert riga.nota_id == nota.pk
        assert riga.importo == Decimal("15.50")

    def test_categoria_chilometrica_e_rifiutata(self, nota, capo_utente) -> None:
        categoria_km = CategoriaSpesa.objects.create(
            nome="Auto test",
            tipo_calcolo=TipoCalcolo.CHILOMETRICO,
            sottotipo_chilometrico="ALTRO",
        )
        with pytest.raises(ValidationError):
            aggiungi_riga_documentale(
                nota=nota,
                utente=capo_utente,
                categoria=categoria_km,
                data=datetime.date(2027, 7, 2),
                importo=Decimal("10"),
            )

    def test_descrizione_obbligatoria_verificata(self, nota, capo_utente) -> None:
        categoria = CategoriaSpesa.objects.create(
            nome="Materiale test", descrizione_obbligatoria=True
        )
        with pytest.raises(ValidationError):
            aggiungi_riga_documentale(
                nota=nota,
                utente=capo_utente,
                categoria=categoria,
                data=datetime.date(2027, 7, 2),
                importo=Decimal("10"),
            )

    def test_altro_capo_non_puo_aggiungere_righe(self, nota, categoria_documentale) -> None:
        altro = _persona("altro@example.it", codice_socio="555555X")
        with pytest.raises(PermissionDenied):
            aggiungi_riga_documentale(
                nota=nota,
                utente=altro,
                categoria=categoria_documentale,
                data=datetime.date(2027, 7, 2),
                importo=Decimal("10"),
            )

    def test_nota_non_in_bozza_blocca_aggiunta(
        self, nota, capo_utente, categoria_documentale
    ) -> None:
        NotaSpese.objects.filter(pk=nota.pk).update(stato=StatoNota.INVIATA)
        nota.refresh_from_db()
        with pytest.raises(ValidationError):
            aggiungi_riga_documentale(
                nota=nota,
                utente=capo_utente,
                categoria=categoria_documentale,
                data=datetime.date(2027, 7, 2),
                importo=Decimal("10"),
            )
