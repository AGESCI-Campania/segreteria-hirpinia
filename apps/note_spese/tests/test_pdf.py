"""F8/D-67: contenuto del PDF della nota. `contesto_pdf_nota()` non importa
WeasyPrint (l'import resta dentro `genera_pdf_nota()`), quindi questi test
girano senza le librerie native Pango/Cairo — la generazione vera del PDF è
testata solo a livello di view (`test_views_pdf.py`)."""

import datetime
from decimal import Decimal

import pytest

from apps.anagrafica.models import Capo
from apps.note_spese.models import (
    AutorizzazioneRdzConfig,
    CategoriaSpesa,
    Evento,
    ImpostazioniNoteSpese,
    NotaSpese,
    RigaSpesa,
)
from apps.note_spese.pdf import contesto_pdf_nota
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="1A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


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
def nota(gruppo, capo, evento, treno, vitto) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        numero="2027/0001",
        iban="IT60X0542811101000000123456",
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=treno, data=datetime.date(2027, 7, 2), importo=Decimal("30.00")
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=vitto, data=datetime.date(2027, 7, 2), importo=Decimal("12.50")
    )
    return nota


class TestContestoPdfNota:
    def test_totali_per_categoria_principale(self, nota) -> None:
        contesto = contesto_pdf_nota(nota)
        assert dict(contesto["totali_categoria"]) == {
            "Viaggio": Decimal("30.00"),
            "Logistica": Decimal("12.50"),
        }
        assert contesto["totale_riconosciuto"] == Decimal("42.50")

    def test_iban_mascherato(self, nota) -> None:
        contesto = contesto_pdf_nota(nota)
        assert "IT60X0542811101000000123456" not in contesto["iban_mascherato"]
        assert contesto["iban_mascherato"].endswith("3456")

    def test_doppia_firma_rdz_riflette_impostazioni(self, nota) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.DOPPIA}
        )
        assert contesto_pdf_nota(nota)["doppia_firma_rdz"] is True

        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.SINGOLA}
        )
        assert contesto_pdf_nota(nota)["doppia_firma_rdz"] is False

    def test_totale_richiesto_usa_importo_originale_se_corretto(self, nota) -> None:
        riga = nota.righe.get(categoria__nome="Treno")
        riga.importo_originale = Decimal("35.00")
        riga.save()

        contesto = contesto_pdf_nota(nota)

        assert contesto["totale_richiesto"] == Decimal("35.00") + Decimal("12.50")
        assert contesto["totale_riconosciuto"] == Decimal("42.50")

    def test_loghi_trovati_negli_static(self, nota) -> None:
        contesto = contesto_pdf_nota(nota)
        assert contesto["logo_zona_path"] is not None
        assert contesto["loghi_piede_path"] is not None
