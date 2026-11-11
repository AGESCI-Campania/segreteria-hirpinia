"""Etichetta 50×80 mm del codice di voto (apps/voto/etichetta.py)."""

import base64
import io
import logging
import re

import pytest
from PIL import Image
from pypdf import PdfReader

from apps.voto import codici, etichetta
from apps.voto.models import CodiceVoto

from .conftest import avente

ESEMPIO = etichetta.Etichetta(
    codice="K7QM-R4XP-2W",
    link="https://example.it/voto/#c=K7QMR4XP2W",
    nome="Mariangela Di Bartolomeo",
    assemblea="Assemblea primaverile 2026/2027",
    convocazione="Prima convocazione del 10/04/2027",
)


def test_png_50x80_in_bianco_e_nero():
    immagine = Image.open(io.BytesIO(etichetta.png(ESEMPIO)))
    assert immagine.mode == "1"
    larghezza_mm = immagine.width / etichetta.DPI * 25.4
    altezza_mm = immagine.height / etichetta.DPI * 25.4
    assert round(larghezza_mm) == 50 and round(altezza_mm) == 80
    assert round(immagine.info["dpi"][0]) == etichetta.DPI


def test_pdf_una_pagina_50x80():
    lettore = PdfReader(io.BytesIO(etichetta.pdf(ESEMPIO)))
    assert len(lettore.pages) == 1
    pagina = lettore.pages[0]
    assert round(float(pagina.mediabox.width) / 72 * 25.4) == 50
    assert round(float(pagina.mediabox.height) / 72 * 25.4) == 80
    testo = pagina.extract_text()
    assert "K7QM-R4XP-2W" in testo and "Mariangela Di Bartolomeo" in testo


def test_data_uri():
    assert etichetta.data_uri(b"ab", "image/png") == "data:image/png;base64,YWI="


@pytest.mark.django_db
def test_rigenera_e_mostra_porta_l_etichetta_senza_registrarla(
    client, seduta, assemblea, operatore, caplog
):
    caplog.set_level(logging.DEBUG)
    client.force_login(operatore)
    gialli = avente(assemblea, "Gialli")
    url = f"/voto/gestione/{assemblea.pk}/sedute/{seduta.pk}/codici/{gialli.pk}/mostra/"
    testo = client.post(url).content.decode()
    png = re.search(r'href="data:image/png;base64,([^"]+)" download="codice-voto.png"', testo)
    pdf = re.search(r'href="data:application/pdf;base64,([^"]+)" download="codice-voto.pdf"', testo)
    assert png and pdf
    contenuto = PdfReader(io.BytesIO(base64.b64decode(pdf.group(1)))).pages[0].extract_text()
    codice = re.search(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{2}", contenuto).group(0)
    assert codici.calcola_hash(codice) == CodiceVoto.objects.get(avente=gialli).hash
    assert "Sara Gialli" in contenuto
    # Il codice non finisce nei log.
    assert codice not in caplog.text and codice.replace("-", "") not in caplog.text
