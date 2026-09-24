"""PDF della nota (D-67, F8). WeasyPrint importato in modo lazy dentro
`genera_pdf_nota()`/`_pdf_pagina_giustificativo()` (stesso motivo di
`apps.contributi.views.CampagnaReportPdfView`): le librerie native
(Pango/Cairo) non sono sempre disponibili nell'ambiente di import.

**Giustificativi in coda (punto 8 di D-67)**: un'immagine (sempre JPEG dopo
F5) è incorporata come `data:` URI in una pagina con intestazione "Riga N";
un PDF (A-11: "resta intatto, possibile valore fiscale") è preceduto dalla
stessa pagina di intestazione ma **mai riscritto/timbrato** — le sue pagine
originali sono unite così come sono con `pypdf`. Entrambi i casi leggono i
byte con `Allegato.file.read()`, mai un percorso di filesystem: lo storage
è configurabile (D-59) e potrebbe non essere locale.

**Deviazioni dichiarate rispetto al testo di D-67** (dati che il modello
non ha o non valorizza ancora, verificato con `rg`, non assunto):
- Nessun campo "luogo" su `Evento` — il riquadro evento non lo mostra.
- Nessuna "tariffa applicata" persistita per riga (`calcolo_riga_auto.py`
  la usa per calcolare `RigaSpesa.importo` ma non la salva): mostrata solo
  la distanza, non la tariffa, per non ricalcolarla/indovinarla in stampa.
- Il riquadro di liquidazione mostra `data_pagamento`/`riferimento_tracciabilita`
  se valorizzati: oggi non lo sono mai (gap già segnalato in
  docs/TODO.md), restano vuoti in stampa."""

from __future__ import annotations

import base64
import io
from decimal import Decimal

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from pypdf import PdfReader, PdfWriter

from .categorie import mappa_categoria_principale
from .iban import maschera_iban
from .models import Allegato, AutorizzazioneRdzConfig, ImpostazioniNoteSpese, NotaSpese, RigaSpesa


def _totali_per_categoria(righe) -> list[tuple[str, Decimal]]:
    mappa = mappa_categoria_principale()
    totali: dict[int, Decimal] = {}
    nomi: dict[int, str] = {}
    for riga in righe:
        principale = mappa[riga.categoria_id]
        importo = riga.importo or Decimal("0")
        totali[principale.pk] = totali.get(principale.pk, Decimal("0")) + importo
        nomi[principale.pk] = principale.nome
    return sorted(((nomi[pk], totale) for pk, totale in totali.items()), key=lambda x: x[0])


def contesto_pdf_nota(nota: NotaSpese) -> dict:
    righe = list(
        nota.righe.select_related("categoria", "localita_partenza", "localita_arrivo")
        .prefetch_related("passeggeri", "allegati")
        .all()
    )
    totale_richiesto = sum(
        (r.importo_originale or r.importo or Decimal("0") for r in righe), Decimal("0")
    )
    totale_riconosciuto = sum((r.importo or Decimal("0") for r in righe), Decimal("0"))
    return {
        "nota": nota,
        "righe": righe,
        "iban_mascherato": maschera_iban(nota.iban),
        "totali_categoria": _totali_per_categoria(righe),
        "totale_richiesto": totale_richiesto,
        "totale_riconosciuto": totale_riconosciuto,
        "doppia_firma_rdz": (
            ImpostazioniNoteSpese.corrente().autorizzazione_rdz == AutorizzazioneRdzConfig.DOPPIA
        ),
        "autorizzazioni_rdz": nota.autorizzazioni_rdz.select_related("utente"),
        "logo_zona_path": finders.find("note_spese/img/logo_zona.png"),
        "loghi_piede_path": finders.find("note_spese/img/loghi_wosm_waggs.png"),
    }


def _e_pdf(contenuto: bytes) -> bool:
    return contenuto[:5] == b"%PDF-"


def _pdf_pagina_giustificativo(
    numero_riga: int, riga: RigaSpesa, immagine_base64: str | None
) -> bytes:
    from weasyprint import HTML

    html = render_to_string(
        "note_spese/nota_pdf_giustificativo.html",
        {"numero_riga": numero_riga, "riga": riga, "immagine_base64": immagine_base64},
    )
    return HTML(string=html).write_pdf()


def _pagine_giustificativi(righe: list[RigaSpesa]) -> list[bytes]:
    """Una voce per pagina generata (immagine) o gruppo di pagine originali
    (PDF), nell'ordine delle righe della tabella — coerente con la
    numerazione "N." aggiunta lì (D-67, "riferimento al numero di riga")."""
    parti: list[bytes] = []
    for numero_riga, riga in enumerate(righe, start=1):
        allegato: Allegato
        for allegato in riga.allegati.all():
            allegato.file.open("rb")
            try:
                contenuto = allegato.file.read()
            finally:
                allegato.file.close()
            if _e_pdf(contenuto):
                parti.append(_pdf_pagina_giustificativo(numero_riga, riga, None))
                parti.append(contenuto)
            else:
                immagine_base64 = base64.b64encode(contenuto).decode("ascii")
                parti.append(_pdf_pagina_giustificativo(numero_riga, riga, immagine_base64))
    return parti


def _unisci_pdf(corpo: bytes, parti: list[bytes]) -> bytes:
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(corpo)))
    for parte in parti:
        writer.append(PdfReader(io.BytesIO(parte)))
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def genera_pdf_nota(nota: NotaSpese) -> bytes:
    from weasyprint import HTML

    contesto = contesto_pdf_nota(nota)
    corpo = HTML(string=render_to_string("note_spese/nota_pdf.html", contesto)).write_pdf()

    parti_giustificativi = _pagine_giustificativi(contesto["righe"])
    if not parti_giustificativi:
        return corpo
    return _unisci_pdf(corpo, parti_giustificativi)
