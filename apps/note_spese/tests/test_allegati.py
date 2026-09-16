"""D-58/A-11: validazione e normalizzazione degli allegati."""

import datetime
import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.allegati import (
    DIMENSIONE_MASSIMA_BYTE,
    NUMERO_MASSIMO_FILE_PER_RIGA,
    carica_allegato,
    prepara_contenuto,
    valida_allegati_obbligatori,
    valida_dimensione,
    valida_numero_massimo_per_riga,
)
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese, RigaSpesa
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def nota(gruppo, capo, evento) -> NotaSpese:
    return NotaSpese.objects.create(
        beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )


@pytest.fixture
def categoria_documentale() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test allegati", richiede_allegato=True)


@pytest.fixture
def categoria_auto() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(
        nome="Auto test allegati",
        tipo_calcolo="CHILOMETRICO",
        sottotipo_chilometrico="ALTRO",
        richiede_allegato=False,
    )


@pytest.fixture
def utente(capo) -> Utente:
    return Utente.objects.create(
        username="u-allegati",
        email="mario@example.it",
        tipo=TipoUtente.PERSONA,
        codice_socio=capo.pk,
    )


def _pdf(dimensione_padding: int = 0) -> SimpleUploadedFile:
    contenuto = b"%PDF-1.4\n" + b"0" * dimensione_padding + b"\n%%EOF"
    return SimpleUploadedFile("documento.pdf", contenuto, content_type="application/pdf")


def _immagine(formato: str = "JPEG", size: tuple[int, int] = (3000, 1000)) -> SimpleUploadedFile:
    img = Image.new("RGB", size, color=(10, 20, 30))
    buffer = io.BytesIO()
    if formato == "HEIF":
        import pillow_heif

        pillow_heif.register_heif_opener()
    img.save(buffer, format=formato)
    buffer.seek(0)
    estensione = {"JPEG": "jpg", "PNG": "png", "HEIF": "heic"}[formato]
    tipo = {"JPEG": "image/jpeg", "PNG": "image/png", "HEIF": "image/heic"}[formato]
    return SimpleUploadedFile(f"foto.{estensione}", buffer.read(), content_type=tipo)


class TestValidaDimensione:
    def test_file_entro_il_limite_e_valido(self) -> None:
        valida_dimensione(_pdf())

    def test_file_oltre_il_limite_solleva_errore(self) -> None:
        oversize = SimpleUploadedFile(
            "grande.pdf", b"%" * (DIMENSIONE_MASSIMA_BYTE + 1), content_type="application/pdf"
        )
        with pytest.raises(ValidationError):
            valida_dimensione(oversize)


class TestValidaNumeroMassimoPerRiga:
    def test_sotto_il_limite_e_valido(self, nota, categoria_documentale) -> None:
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        valida_numero_massimo_per_riga(riga)

    def test_al_limite_esatto_solleva_errore(self, nota, categoria_documentale, utente) -> None:
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        for _ in range(NUMERO_MASSIMO_FILE_PER_RIGA):
            carica_allegato(_pdf(), [riga], utente)
        with pytest.raises(ValidationError):
            valida_numero_massimo_per_riga(riga)


class TestPreparaContenuto:
    def test_pdf_resta_intatto(self) -> None:
        file = _pdf()
        contenuto_originale = file.read()
        file.seek(0)
        contenuto, tipo = prepara_contenuto(file)
        assert tipo == "application/pdf"
        assert contenuto.read() == contenuto_originale

    def test_jpeg_viene_ricompresso_e_ridimensionato(self) -> None:
        contenuto, tipo = prepara_contenuto(_immagine("JPEG", (3000, 1000)))
        assert tipo == "image/jpeg"
        immagine = Image.open(contenuto)
        assert immagine.format == "JPEG"
        assert max(immagine.size) <= 2000

    def test_png_viene_convertito_in_jpeg(self) -> None:
        contenuto, tipo = prepara_contenuto(_immagine("PNG", (500, 300)))
        assert tipo == "image/jpeg"
        immagine = Image.open(contenuto)
        assert immagine.format == "JPEG"

    def test_heic_viene_convertito_in_jpeg(self) -> None:
        contenuto, tipo = prepara_contenuto(_immagine("HEIF", (500, 300)))
        assert tipo == "image/jpeg"
        immagine = Image.open(contenuto)
        assert immagine.format == "JPEG"

    def test_immagine_piu_piccola_del_limite_non_viene_ingrandita(self) -> None:
        contenuto, _ = prepara_contenuto(_immagine("JPEG", (100, 80)))
        immagine = Image.open(contenuto)
        assert immagine.size == (100, 80)

    def test_formato_non_ammesso_solleva_errore(self) -> None:
        img = Image.new("RGB", (10, 10))
        buffer = io.BytesIO()
        img.save(buffer, format="BMP")
        buffer.seek(0)
        file = SimpleUploadedFile("foto.bmp", buffer.read(), content_type="image/bmp")
        with pytest.raises(ValidationError):
            prepara_contenuto(file)

    def test_file_non_immagine_non_pdf_solleva_errore(self) -> None:
        file = SimpleUploadedFile("testo.txt", b"non un file valido", content_type="text/plain")
        with pytest.raises(ValidationError):
            prepara_contenuto(file)


class TestCaricaAllegato:
    def test_crea_allegato_collegato_a_piu_righe(self, nota, categoria_documentale, utente) -> None:
        riga1 = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        riga2 = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 3)
        )
        allegato = carica_allegato(_pdf(), [riga1, riga2], utente)
        assert set(allegato.righe.all()) == {riga1, riga2}
        assert allegato.caricato_da == utente

    def test_senza_righe_solleva_errore(self, utente) -> None:
        with pytest.raises(ValidationError):
            carica_allegato(_pdf(), [], utente)

    def test_supera_il_limite_su_una_sola_riga_blocca_tutto(
        self, nota, categoria_documentale, utente
    ) -> None:
        riga_piena = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        riga_libera = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 3)
        )
        for _ in range(NUMERO_MASSIMO_FILE_PER_RIGA):
            carica_allegato(_pdf(), [riga_piena], utente)
        with pytest.raises(ValidationError):
            carica_allegato(_pdf(), [riga_piena, riga_libera], utente)
        assert riga_libera.allegati.count() == 0


class TestValidaAllegatiObbligatori:
    def test_categoria_che_richiede_allegato_senza_file_blocca(
        self, nota, categoria_documentale
    ) -> None:
        RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        with pytest.raises(ValidationError):
            valida_allegati_obbligatori(nota)

    def test_categoria_che_richiede_allegato_con_file_passa(
        self, nota, categoria_documentale, utente
    ) -> None:
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        carica_allegato(_pdf(), [riga], utente)
        valida_allegati_obbligatori(nota)

    def test_categoria_auto_non_richiede_allegato(self, nota, categoria_auto) -> None:
        RigaSpesa.objects.create(
            nota=nota, categoria=categoria_auto, data=datetime.date(2027, 7, 2)
        )
        valida_allegati_obbligatori(nota)
