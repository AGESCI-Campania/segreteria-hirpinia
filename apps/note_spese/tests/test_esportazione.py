"""F8/D-68: servizio unico di esportazione (quattro raggruppamenti)."""

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.esportazione import RaggruppamentoEsportazione, genera_esportazione
from apps.note_spese.models import (
    CategoriaSpesa,
    CentroCosto,
    Evento,
    NotaSpese,
    RigaSpesa,
    StatoNota,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, codice_socio: str | None = None) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(
        username=f"u{n}",
        email=email,
        tipo=TipoUtente.PERSONA,
        codice_socio=codice_socio,
        stato=StatoUtente.ATTIVO,
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="1A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def viaggio() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Viaggio")


@pytest.fixture
def logistica() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Logistica")


@pytest.fixture
def treno(viaggio) -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Treno", parent=viaggio)


@pytest.fixture
def vitto(logistica) -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto", parent=logistica)


@pytest.fixture
def centro() -> CentroCosto:
    return CentroCosto.objects.create(nome="Zona")


def _nota_liquidata(
    gruppo, capo, evento, anno_contabilizzazione, righe_importi, *, centro_costo=None, numero=None
) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        stato=StatoNota.LIQUIDATA,
        anno_contabilizzazione=anno_contabilizzazione,
        centro_costo=centro_costo,
        numero=numero,
    )
    for categoria, importo in righe_importi:
        RigaSpesa.objects.create(
            nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=importo
        )
    return nota


class TestGeneraEsportazionePerimetro:
    def test_capo_vede_solo_le_proprie_note(self, gruppo, capo, evento, capo_utente, treno) -> None:
        altro_capo = Capo.objects.create(codice_socio="2B", nome="Luigi", cognome="Bianchi")
        _nota_liquidata(gruppo, capo, evento, 2027, [(treno, Decimal("10"))], numero="2027/0001")
        _nota_liquidata(
            gruppo, altro_capo, evento, 2027, [(treno, Decimal("20"))], numero="2027/0002"
        )

        risultato = genera_esportazione(
            capo_utente,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.CAPO,
        )

        assert len(risultato.righe) == 1
        assert "Rossi Mario" in risultato.righe[0][0]

    def test_solo_anno_di_liquidazione_richiesto(
        self, gruppo, capo, evento, segreteria, treno
    ) -> None:
        _nota_liquidata(gruppo, capo, evento, 2026, [(treno, Decimal("10"))], numero="2026/0001")
        _nota_liquidata(gruppo, capo, evento, 2027, [(treno, Decimal("20"))], numero="2027/0001")

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.CAPO,
        )

        assert len(risultato.righe) == 1
        assert risultato.righe[0][1] == "20.00"

    def test_note_non_liquidate_escluse(self, gruppo, capo, evento, segreteria, treno) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            stato=StatoNota.APPROVATA,
        )
        RigaSpesa.objects.create(
            nota=nota, categoria=treno, data=datetime.date(2027, 7, 2), importo=Decimal("10")
        )

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.CAPO,
        )

        assert risultato.righe == []


class TestRaggruppamenti:
    def test_per_centro_costo_somma_correttamente(
        self, gruppo, capo, evento, segreteria, treno, centro
    ) -> None:
        _nota_liquidata(
            gruppo,
            capo,
            evento,
            2027,
            [(treno, Decimal("10"))],
            centro_costo=centro,
            numero="2027/0001",
        )
        _nota_liquidata(
            gruppo,
            capo,
            evento,
            2027,
            [(treno, Decimal("5"))],
            centro_costo=centro,
            numero="2027/0002",
        )

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.CENTRO_COSTO,
        )

        assert risultato.intestazioni == ["Centro di costo", "Totale"]
        assert risultato.righe == [["Zona", "15.00"]]

    def test_per_centro_costo_non_imputato(self, gruppo, capo, evento, segreteria, treno) -> None:
        _nota_liquidata(gruppo, capo, evento, 2027, [(treno, Decimal("10"))], numero="2027/0001")

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.CENTRO_COSTO,
        )

        assert risultato.righe == [["Non imputato", "10.00"]]

    def test_per_evento(self, gruppo, capo, evento, segreteria, treno) -> None:
        _nota_liquidata(gruppo, capo, evento, 2027, [(treno, Decimal("10"))], numero="2027/0001")

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.EVENTO,
        )

        assert risultato.intestazioni == ["Evento", "Totale"]
        assert risultato.righe == [[evento.nome, "10.00"]]

    def test_per_capo(self, gruppo, capo, evento, segreteria, treno) -> None:
        _nota_liquidata(gruppo, capo, evento, 2027, [(treno, Decimal("10"))], numero="2027/0001")

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.CAPO,
        )

        assert risultato.intestazioni == ["Capo", "Totale"]
        assert risultato.righe == [["Rossi Mario (1A)", "10.00"]]

    def test_bilancio_colonne_dinamiche_e_totali(
        self, gruppo, capo, evento, segreteria, treno, vitto
    ) -> None:
        _nota_liquidata(
            gruppo,
            capo,
            evento,
            2027,
            [(treno, Decimal("10")), (vitto, Decimal("5"))],
            numero="2027/0001",
        )

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.NESSUNO,
        )

        assert risultato.intestazioni == [
            "Numero",
            "Data pagamento",
            "Evento",
            "Capo",
            "Logistica",
            "Viaggio",
            "Totale",
        ]
        assert risultato.righe == [
            ["2027/0001", "", evento.nome, "Rossi Mario (1A)", "5.00", "10.00", "15.00"]
        ]

    def test_bilancio_colonna_assente_se_categoria_non_usata(
        self, gruppo, capo, evento, segreteria, treno, vitto
    ) -> None:
        """Solo le categorie principali realmente presenti in questo lotto
        di note diventano colonne — non tutte quelle anagrafiche esistenti."""
        _nota_liquidata(gruppo, capo, evento, 2027, [(treno, Decimal("10"))], numero="2027/0001")

        risultato = genera_esportazione(
            segreteria,
            anno_liquidazione=2027,
            raggruppamento=RaggruppamentoEsportazione.NESSUNO,
        )

        assert "Logistica" not in risultato.intestazioni
        assert "Viaggio" in risultato.intestazioni
