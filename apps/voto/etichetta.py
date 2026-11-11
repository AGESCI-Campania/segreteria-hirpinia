"""Etichetta 50×80 mm del codice di voto, per un'etichettatrice termica come la
Niimbot B1 (docs/plan_preparazione_assemblea.md, R8, D23-D25).

Verticale (50 mm di larghezza, 80 di altezza) con il contenuto entro 48 mm;
codice a gruppi, QR del link all'urna (codice nel fragment), assemblea,
convocazione e nome del capo. Si genera **solo in memoria**, nella stessa
risposta di «Rigenera e mostra» (`views.CodiceMostraView`): il codice non
passa da un'altra richiesta, dall'URL, dalla sessione o dal disco (D-71), e
qui non si registra nulla."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import segno
from django.template.loader import render_to_string
from PIL import Image, ImageDraw, ImageFont

# Risoluzione della stampante: 203 dpi è quella dichiarata per la B1 (da
# verificare con la stampante; cambia solo la nitidezza, non le misure).
DPI = 203
LARGHEZZA_MM = 50
ALTEZZA_MM = 80
MARGINE_MM = 1


def _px(mm: float) -> int:
    return round(mm / 25.4 * DPI)


@dataclass(frozen=True)
class Etichetta:
    codice: str  # già formattato a gruppi
    link: str
    nome: str
    assemblea: str
    convocazione: str


def _font(dimensione: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Il font incorporato in Pillow: nessun file di font da installare.
    return ImageFont.load_default(size=dimensione)


def _righe(disegno: ImageDraw.ImageDraw, testo: str, font, larghezza: int) -> list[str]:
    righe: list[str] = []
    corrente = ""
    for parola in testo.split():
        prova = f"{corrente} {parola}".strip()
        if disegno.textlength(prova, font=font) <= larghezza or not corrente:
            corrente = prova
        else:
            righe.append(corrente)
            corrente = parola
    if corrente:
        righe.append(corrente)
    return righe


def _centra(disegno, y: int, testo: str, font, larghezza_pagina: int) -> int:
    sinistra, alto, destra, basso = disegno.textbbox((0, 0), testo, font=font)
    disegno.text(
        ((larghezza_pagina - (destra - sinistra)) / 2 - sinistra, y), testo, font=font, fill=0
    )
    return y + (basso - alto) + _px(1)


def png(etichetta: Etichetta) -> bytes:
    """PNG in bianco e nero puro (1 bit), alla risoluzione della stampante."""
    larghezza, altezza, margine = _px(LARGHEZZA_MM), _px(ALTEZZA_MM), _px(MARGINE_MM)
    utile = larghezza - 2 * margine
    immagine = Image.new("1", (larghezza, altezza), 1)
    disegno = ImageDraw.Draw(immagine)

    y = margine + _px(1)
    piccolo = _font(_px(2.6))
    for riga in _righe(disegno, etichetta.assemblea, piccolo, utile):
        y = _centra(disegno, y, riga, piccolo, larghezza)
    y = _centra(disegno, y, etichetta.convocazione, piccolo, larghezza)
    y += _px(1)
    medio = _font(_px(3.6))
    for riga in _righe(disegno, etichetta.nome, medio, utile):
        y = _centra(disegno, y, riga, medio, larghezza)

    # QR al centro, il più grande possibile entro i margini.
    qr = segno.make(etichetta.link, error="m")
    buffer = io.BytesIO()
    lato_moduli = qr.symbol_size(scale=1, border=2)[0]
    scala = max(1, utile // lato_moduli)
    qr.save(buffer, kind="png", scale=scala, border=2)
    immagine_qr = Image.open(io.BytesIO(buffer.getvalue())).convert("1")
    y += _px(1)
    immagine.paste(immagine_qr, ((larghezza - immagine_qr.width) // 2, y))
    y += immagine_qr.height + _px(1)

    # Codice grande: la dimensione si riduce finché ci sta nella larghezza utile.
    dimensione = _px(6)
    grande = _font(dimensione)
    while disegno.textlength(etichetta.codice, font=grande) > utile and dimensione > 10:
        dimensione -= 2
        grande = _font(dimensione)
    _centra(disegno, y, etichetta.codice, grande, larghezza)

    uscita = io.BytesIO()
    immagine.save(uscita, format="PNG", dpi=(DPI, DPI))
    return uscita.getvalue()


def pdf(etichetta: Etichetta) -> bytes:
    """PDF di una pagina 50×80 mm (WeasyPrint, importato solo qui)."""
    from weasyprint import HTML

    qr = segno.make(etichetta.link, error="m").svg_data_uri(scale=4, dark="#000", light="#fff")
    html = render_to_string("voto/etichetta_pdf.html", {"etichetta": etichetta, "qr": qr})
    return HTML(string=html).write_pdf()


def data_uri(contenuto: bytes, tipo: str) -> str:
    return f"data:{tipo};base64,{base64.b64encode(contenuto).decode('ascii')}"
