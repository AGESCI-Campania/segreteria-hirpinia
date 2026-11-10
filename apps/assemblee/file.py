"""File dell'assemblea (D-70): tracciato per l'app di voto del Nazionale e
foglio presenze cartaceo. WeasyPrint importato in modo lazy, come negli altri
PDF del progetto (le librerie native non sono sempre disponibili all'import)."""

from __future__ import annotations

import io

from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.utils import timezone
from openpyxl import Workbook

from apps.accounts.models import Utente
from apps.core.pdf import percorsi_carta_intestata

from .models import Assemblea, AventeDiritto, ScaricamentoFile, Seduta, TipoFile
from .permessi import puo_gestire_assemblee

# Tracciato dell'app di voto: intestazione alla riga 6 (5 righe vuote prima),
# foglio "Sheet1", come il modello fornito dal Nazionale.
RIGA_INTESTAZIONE = 6
INTESTAZIONE_TRACCIATO = [
    "SubID",
    "PIC",
    "Codice",
    "Nome",
    "Cognome",
    "Gruppo",
    "Città",
    "PR",
    "Regione",
    "Status",
    "Email",
    "Cell",
    "Email Cap",
    "Cell Capo",
    "E1",
    "E2",
    "Presente:",
    "Diritto di voto",
    "Codice delegato",
]
REGIONE = "CAMPANIA"
STATUS = "RINNOVO ADESIONE"
# Segnaposto quando l'anagrafica non ha il recapito: l'app li ignora.
EMAIL_SEGNAPOSTO = "xxx@yyy.it"
CELLULARE_SEGNAPOSTO = "3217654321"


def _verifica_gestore(utente: Utente) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied


def _traccia(assemblea: Assemblea, tipo: str, utente: Utente, righe: int) -> None:
    ScaricamentoFile.objects.create(
        assemblea=assemblea, tipo=tipo, utente=utente, numero_righe=righe
    )


def seduta_in_corso(assemblea: Assemblea) -> Seduta | None:
    """L'ultima convocazione creata: quella a cui si riferiscono presenze e file."""
    return assemblea.sedute.order_by("-convocazione").first()


def _codice(codice_socio: str) -> int | str:
    # Nel modello il codice socio è un numero; un codice non numerico resta testo.
    return int(codice_socio) if codice_socio.isdigit() else codice_socio


def righe_tracciato(assemblea: Assemblea) -> list[list]:
    """Solo chi vota in app ed è nell'elenco; gruppo di origine (quello che
    l'app conosce da BuonaStrada), anche dopo un trasferimento."""
    aventi = (
        assemblea.aventi_diritto.nell_elenco()
        .filter(vota_in_app=True)
        .select_related("capo", "gruppo", "gruppo_origine")
        .order_by("cognome", "nome")
    )
    righe = []
    for pic, avente in enumerate(aventi, start=1):
        gruppo = avente.gruppo_origine or avente.gruppo
        capo = avente.capo
        righe.append(
            [
                assemblea.anno_scout,
                pic,
                _codice(avente.codice_socio),
                avente.nome,
                avente.cognome,
                gruppo.nome,
                None,
                None,
                REGIONE,
                STATUS,
                (capo.email if capo and capo.email else EMAIL_SEGNAPOSTO),
                (capo.cellulare if capo and capo.cellulare else CELLULARE_SEGNAPOSTO),
                None,
                None,
                None,
                None,
                # Presenze e deleghe arrivano con la registrazione in sala (Fase 2).
                "NO",
                "SI",
                None,
            ]
        )
    return righe


def genera_tracciato_xlsx(assemblea: Assemblea, utente: Utente) -> bytes:
    _verifica_gestore(utente)
    righe = righe_tracciato(assemblea)
    cartella = Workbook()
    foglio = cartella.active
    assert foglio is not None
    foglio.title = "Sheet1"
    for colonna, titolo in enumerate(INTESTAZIONE_TRACCIATO, start=1):
        foglio.cell(row=RIGA_INTESTAZIONE, column=colonna, value=titolo)
    for numero, riga in enumerate(righe, start=RIGA_INTESTAZIONE + 1):
        for colonna, valore in enumerate(riga, start=1):
            if valore is not None:
                foglio.cell(row=numero, column=colonna, value=valore)
    buffer = io.BytesIO()
    cartella.save(buffer)
    _traccia(assemblea, TipoFile.TRACCIATO_APP, utente, len(righe))
    return buffer.getvalue()


def gruppi_foglio_presenze(
    assemblea: Assemblea,
) -> list[tuple[str, list[tuple[int, AventeDiritto]]]]:
    """Aventi diritto raggruppati per gruppo attuale (dopo i trasferimenti),
    in ordine di gruppo e cognome, con un numero progressivo unico su tutto
    il foglio."""
    aventi = (
        assemblea.aventi_diritto.nell_elenco()
        .select_related("gruppo")
        .order_by("gruppo__nome", "cognome", "nome")
    )
    gruppi: list[tuple[str, list[tuple[int, AventeDiritto]]]] = []
    for numero, avente in enumerate(aventi, start=1):
        if not gruppi or gruppi[-1][0] != avente.gruppo.nome:
            gruppi.append((avente.gruppo.nome, []))
        gruppi[-1][1].append((numero, avente))
    return gruppi


def genera_foglio_presenze_pdf(assemblea: Assemblea, utente: Utente) -> bytes:
    from weasyprint import HTML

    _verifica_gestore(utente)
    gruppi = gruppi_foglio_presenze(assemblea)
    totale = sum(len(righe) for _, righe in gruppi)
    contesto = {
        "assemblea": assemblea,
        "seduta": seduta_in_corso(assemblea),
        "gruppi": gruppi,
        "totale": totale,
        "totale_app": sum(a.vota_in_app for _, righe in gruppi for _, a in righe),
        "righe_vuote": range(2),
        "generato_il": timezone.localtime(),
        **percorsi_carta_intestata(),
    }
    pdf = HTML(string=render_to_string("assemblee/foglio_presenze_pdf.html", contesto)).write_pdf()
    _traccia(assemblea, TipoFile.FOGLIO_PRESENZE, utente, totale)
    return pdf
