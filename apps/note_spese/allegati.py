"""Validazione e normalizzazione dei giustificativi (D-58, A-11): dimensione,
numero massimo per riga, conversione HEIC→JPEG, compressione immagini. I PDF
non si ricomprimono mai: possono avere valore fiscale (A-11) — solo le
immagini perdono l'originale, come esplicitamente previsto."""

from __future__ import annotations

import io

import pillow_heif
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from PIL import Image, ImageOps

from apps.accounts.models import Utente

from .models import Allegato, NotaSpese, RigaSpesa

pillow_heif.register_heif_opener()

DIMENSIONE_MASSIMA_BYTE = 10 * 1024 * 1024
NUMERO_MASSIMO_FILE_PER_RIGA = 10
LATO_LUNGO_MASSIMO_PX = 2000
QUALITA_JPEG = 85
_FORMATI_IMMAGINE_AMMESSI = {"JPEG", "PNG", "HEIF"}


def valida_dimensione(file: UploadedFile) -> None:
    if file.size is not None and file.size > DIMENSIONE_MASSIMA_BYTE:
        raise ValidationError("Il file supera la dimensione massima di 10 MB (A-11).")


def valida_numero_massimo_per_riga(riga: RigaSpesa, nuovi_file: int = 1) -> None:
    if riga.allegati.count() + nuovi_file > NUMERO_MASSIMO_FILE_PER_RIGA:
        raise ValidationError(
            f"Non si possono avere più di {NUMERO_MASSIMO_FILE_PER_RIGA} allegati per riga (A-11)."
        )


def _e_pdf(file: UploadedFile) -> bool:
    file.seek(0)
    intestazione = file.read(5)
    file.seek(0)
    return intestazione == b"%PDF-"


def _rinomina(nome_originale: str | None, nuova_estensione: str) -> str:
    base = (nome_originale or "allegato").rsplit(".", 1)[0]
    return f"{base}.{nuova_estensione}"


def prepara_contenuto(file: UploadedFile) -> tuple[ContentFile, str]:
    """A-11: PDF salvato intatto; ogni immagine ammessa (JPEG/PNG/HEIC)
    viene invece ricompressa in JPEG (lato lungo max 2000px, qualità 85) —
    l'originale non si conserva, solo per le immagini, come richiesto."""
    valida_dimensione(file)

    if _e_pdf(file):
        return ContentFile(file.read(), name=_rinomina(file.name, "pdf")), "application/pdf"

    try:
        immagine_caricata = Image.open(file)
        immagine_caricata.load()
    except Exception as errore:
        raise ValidationError(
            "Formato non riconosciuto: sono ammessi solo PDF, JPEG, PNG, HEIC (A-11)."
        ) from errore

    formato = (immagine_caricata.format or "").upper()
    if formato not in _FORMATI_IMMAGINE_AMMESSI:
        raise ValidationError(
            f"Formato immagine non ammesso ({formato or 'sconosciuto'}): "
            "sono ammessi solo PDF, JPEG, PNG, HEIC (A-11)."
        )

    immagine: Image.Image = ImageOps.exif_transpose(immagine_caricata)
    if immagine.mode not in ("RGB", "L"):
        immagine = immagine.convert("RGB")
    immagine.thumbnail((LATO_LUNGO_MASSIMO_PX, LATO_LUNGO_MASSIMO_PX))

    buffer = io.BytesIO()
    immagine.save(buffer, format="JPEG", quality=QUALITA_JPEG)
    buffer.seek(0)
    return ContentFile(buffer.read(), name=_rinomina(file.name, "jpg")), "image/jpeg"


@transaction.atomic
def carica_allegato(file: UploadedFile, righe: list[RigaSpesa], utente: Utente) -> Allegato:
    """D-58: un allegato può coprire più righe (documento cumulativo). Il
    limite di 10 file per riga (A-11) si verifica su **ciascuna** riga
    coinvolta prima di procedere."""
    if not righe:
        raise ValidationError("Un allegato deve essere collegato ad almeno una riga.")
    for riga in righe:
        valida_numero_massimo_per_riga(riga)

    contenuto, _content_type = prepara_contenuto(file)
    allegato = Allegato.objects.create(file=contenuto, caricato_da=utente)
    allegato.righe.set(righe)
    return allegato


def valida_allegati_obbligatori(nota: NotaSpese) -> None:
    """D-58: obbligatori per tutte le categorie **tranne** Auto (rimborso
    chilometrico) — il flag è `CategoriaSpesa.richiede_allegato`, mai
    dedotto dal nome. Richiamata da `transizioni.invia_nota` (F3): una nota
    senza i giustificativi richiesti non può essere inviata."""
    righe_senza_allegato = [
        riga
        for riga in nota.righe.select_related("categoria").prefetch_related("allegati")
        if riga.categoria.richiede_allegato and not riga.allegati.exists()
    ]
    if righe_senza_allegato:
        raise ValidationError(
            "Manca il giustificativo per una o più righe che lo richiedono (D-58)."
        )
