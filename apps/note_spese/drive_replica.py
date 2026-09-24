"""Replica su Google Drive alla liquidazione (D-59, F9). I requisiti
chiedono esplicitamente un task Celery asincrono: deciso con Andrea il
2026-09-24 (stessa decisione di F7) di **non** introdurre Celery/Redis
(D-17 resta valido). `enqueue_copie_drive()` è chiamata da
`transizioni.py::liquida()` dentro la stessa transazione — crea solo i
record `CopiaDrive`, nessuna chiamata di rete: così un Drive lento o
irraggiungibile non blocca la transizione di stato, come richiesto. La
copia vera parte da un loop esterno (`note_spese_drive_riconcilia`, stesso
pattern di `note_spese_promemoria`/`note_spese_report_gestori`), che serve
anche come "riconciliazione periodica dei fallimenti" richiesta da D-59."""

from __future__ import annotations

import logging

from .drive import carica_file, replica_configurata
from .models import Allegato, CopiaDrive, NotaSpese, StatoCopiaDrive
from .pdf import genera_pdf_nota

logger = logging.getLogger(__name__)

# Oltre questa soglia una copia FALLITO non viene più ritentata
# automaticamente: resta visibile (stato FALLITO) per un intervento manuale,
# invece di continuare a bussare contro un errore persistente (es. Drive
# condiviso pieno, file rifiutato).
MASSIMO_TENTATIVI = 5


def enqueue_copie_drive(nota: NotaSpese) -> None:
    """D-59: un record per il PDF della nota + uno per ciascun allegato
    distinto delle sue righe — un allegato cumulativo condiviso da più
    righe genera un solo record, non uno per riga che copre. Idempotente
    (`get_or_create`): rieseguire su una nota già in coda non duplica nulla.
    No-op se la replica non è configurata (V-8 non ancora pronto)."""
    if not replica_configurata():
        return

    CopiaDrive.objects.get_or_create(nota=nota, allegato=None)

    allegati_id = Allegato.objects.filter(righe__nota=nota).values_list("pk", flat=True).distinct()
    for allegato_id in allegati_id:
        CopiaDrive.objects.get_or_create(nota=nota, allegato_id=allegato_id)


def _nome_file(copia: CopiaDrive) -> str:
    prefisso = copia.nota.numero or f"nota-{copia.nota_id}"
    allegato = copia.allegato
    if allegato is None:
        return f"{prefisso}.pdf"
    nome_originale = (allegato.file.name or f"allegato-{allegato.pk}").rsplit("/", 1)[-1]
    return f"{prefisso}_{nome_originale}"


def _contenuto_e_tipo(copia: CopiaDrive) -> tuple[bytes, str]:
    allegato = copia.allegato
    if allegato is None:
        return genera_pdf_nota(copia.nota), "application/pdf"

    allegato.file.open("rb")
    try:
        contenuto = allegato.file.read()
    finally:
        allegato.file.close()
    content_type = "application/pdf" if contenuto[:5] == b"%PDF-" else "image/jpeg"
    return contenuto, content_type


def _esegui_copia(copia: CopiaDrive) -> None:
    try:
        contenuto, content_type = _contenuto_e_tipo(copia)
        drive_file_id = carica_file(
            nome=_nome_file(copia), contenuto=contenuto, content_type=content_type
        )
    except Exception as errore:  # requests.HTTPError, errori di rete/auth
        copia.tentativi += 1
        copia.ultimo_errore = str(errore)[:500]
        copia.stato = StatoCopiaDrive.FALLITO
        copia.save(update_fields=["tentativi", "ultimo_errore", "stato", "aggiornata_il"])
        logger.warning(
            "Copia su Drive fallita per CopiaDrive %s (tentativo %s/%s): %s",
            copia.pk,
            copia.tentativi,
            MASSIMO_TENTATIVI,
            errore,
        )
        return

    copia.stato = StatoCopiaDrive.COPIATO
    copia.drive_file_id = drive_file_id
    copia.ultimo_errore = ""
    copia.save(update_fields=["stato", "drive_file_id", "ultimo_errore", "aggiornata_il"])


def riconcilia_copie_drive() -> int:
    """D-59: "riconciliazione periodica dei fallimenti" — ritenta le copie
    IN_ATTESA o FALLITO sotto la soglia di `MASSIMO_TENTATIVI`. Restituisce
    il numero di copie riuscite in questa esecuzione. No-op se la replica
    non è configurata."""
    if not replica_configurata():
        return 0

    da_riprovare = CopiaDrive.objects.filter(
        stato__in=(StatoCopiaDrive.IN_ATTESA, StatoCopiaDrive.FALLITO),
        tentativi__lt=MASSIMO_TENTATIVI,
    ).select_related("nota", "allegato")

    riuscite = 0
    for copia in da_riprovare:
        _esegui_copia(copia)
        if copia.stato == StatoCopiaDrive.COPIATO:
            riuscite += 1
    return riuscite
