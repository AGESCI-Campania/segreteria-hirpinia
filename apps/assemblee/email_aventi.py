"""Email degli aventi diritto per gruppo: export ed import Excel (fase V0 del
voto elettronico, docs/plan_voto.md).

Un file per gruppo da far verificare ai capigruppo in fase di preparazione:
lo si riscarica, lo si corregge, lo si reimporta. L'import segue le regole di
ogni import del progetto (CLAUDE.md): parsing in una funzione pura
(`leggi_excel`), anteprima senza scritture, conferma in `transaction.atomic`
che ricalcola tutto da capo, idempotente, report anomalie persistito in
`ImportazioneEmail`. Aggiorna solo `AventeDiritto.email`, mai l'anagrafica.

L'abbinamento si fa sull'id dell'avente (colonna nascosta): il codice socio
non basta, chi è inserito a mano può non averlo. Il gruppo del file è
scritto in una cella di intestazione: una riga di un altro gruppo blocca
l'import, non viene scartata in silenzio (stesso principio di D-21)."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.text import slugify
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from apps.accounts.models import Utente
from apps.organizzazione.models import Gruppo

from .elenco import normalizza_email
from .models import (
    Assemblea,
    AventeDiritto,
    ImportazioneEmail,
    ScaricamentoFile,
    TipoFile,
)
from .permessi import puo_gestire_assemblee

FOGLIO = "Email"
ETICHETTA_GRUPPO = "Codice gruppo:"
INTESTAZIONE = ["ID", "Cognome", "Nome", "Codice socio", "Email"]
RIGA_INTESTAZIONE = 5
RIGHE_DA_ESAMINARE = 15


def _verifica_gestore(utente: Utente, assemblea: Assemblea) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied


def gruppi_con_aventi(assemblea: Assemblea) -> list[Gruppo]:
    """Gruppi attuali (dopo i trasferimenti) di chi è nell'elenco."""
    codici = assemblea.aventi_diritto.nell_elenco().values_list("gruppo_id", flat=True)
    return list(Gruppo.objects.filter(pk__in=codici).order_by("nome"))


def _aventi_del_gruppo(assemblea: Assemblea, gruppo: Gruppo):
    return assemblea.aventi_diritto.nell_elenco().filter(gruppo=gruppo).order_by("cognome", "nome")


# --- Export ----------------------------------------------------------------------


def _cartella_gruppo(assemblea: Assemblea, gruppo: Gruppo) -> tuple[bytes, int]:
    cartella = Workbook()
    foglio = cartella.active
    assert foglio is not None
    foglio.title = FOGLIO
    foglio["A1"] = f"{assemblea} — {gruppo.nome}"
    foglio["A1"].font = Font(bold=True)
    foglio["A2"] = ETICHETTA_GRUPPO
    foglio["B2"] = gruppo.codice
    foglio["A3"] = (
        "Verificate e completate la colonna Email, poi rimandate il file. "
        "Non modificate la colonna ID (nascosta) né il codice gruppo."
    )
    for colonna, titolo in enumerate(INTESTAZIONE, start=1):
        cella = foglio.cell(row=RIGA_INTESTAZIONE, column=colonna, value=titolo)
        cella.font = Font(bold=True)
    aventi = list(_aventi_del_gruppo(assemblea, gruppo))
    for numero, avente in enumerate(aventi, start=RIGA_INTESTAZIONE + 1):
        valori = [avente.pk, avente.cognome, avente.nome, avente.codice_socio, avente.email]
        for colonna, valore in enumerate(valori, start=1):
            foglio.cell(row=numero, column=colonna, value=valore or None)
    foglio.column_dimensions["A"].hidden = True
    for lettera, larghezza in (("B", 25), ("C", 25), ("D", 15), ("E", 40)):
        foglio.column_dimensions[lettera].width = larghezza
    buffer = io.BytesIO()
    cartella.save(buffer)
    return buffer.getvalue(), len(aventi)


def nome_file_gruppo(assemblea: Assemblea, gruppo: Gruppo) -> str:
    return f"email-{assemblea.anno_scout}-{gruppo.codice}-{slugify(gruppo.nome)}.xlsx"


def genera_excel_gruppo(assemblea: Assemblea, gruppo: Gruppo, utente: Utente) -> bytes:
    _verifica_gestore(utente, assemblea)
    contenuto, righe = _cartella_gruppo(assemblea, gruppo)
    ScaricamentoFile.objects.create(
        assemblea=assemblea, tipo=TipoFile.EMAIL_GRUPPO, utente=utente, numero_righe=righe
    )
    return contenuto


def genera_zip_gruppi(assemblea: Assemblea, utente: Utente) -> bytes:
    """Tutti i file per gruppo in un solo archivio, per distribuirli ai capigruppo."""
    _verifica_gestore(utente, assemblea)
    buffer = io.BytesIO()
    totale = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archivio:
        for gruppo in gruppi_con_aventi(assemblea):
            contenuto, righe = _cartella_gruppo(assemblea, gruppo)
            archivio.writestr(nome_file_gruppo(assemblea, gruppo), contenuto)
            totale += righe
    ScaricamentoFile.objects.create(
        assemblea=assemblea, tipo=TipoFile.EMAIL_GRUPPO, utente=utente, numero_righe=totale
    )
    return buffer.getvalue()


# --- Lettura (funzione pura) -----------------------------------------------------


@dataclass(frozen=True)
class RigaEmail:
    riga: int
    id: str
    cognome: str
    nome: str
    email: str


@dataclass
class LetturaExcel:
    codice_gruppo: str = ""
    righe: list[RigaEmail] = field(default_factory=list)
    errore: str = ""


def _testo(valore) -> str:
    if valore is None:
        return ""
    if isinstance(valore, float) and valore.is_integer():
        valore = int(valore)
    return str(valore).strip()


def leggi_excel(contenuto: bytes) -> LetturaExcel:
    """Legge il file senza toccare il database: codice gruppo e righe grezze.
    Non valida nulla oltre alla struttura (intestazione, codice gruppo)."""
    try:
        cartella = load_workbook(io.BytesIO(contenuto), read_only=True, data_only=True)
    except Exception:  # file non xlsx o corrotto: openpyxl solleva tipi diversi
        return LetturaExcel(errore="Il file non è un Excel (.xlsx) leggibile.")
    foglio = cartella[FOGLIO] if FOGLIO in cartella.sheetnames else cartella.active
    if foglio is None:
        return LetturaExcel(errore="Il file non contiene fogli.")
    lettura = LetturaExcel()
    intestazione = None
    for numero, riga in enumerate(foglio.iter_rows(values_only=True), start=1):
        valori = [_testo(v) for v in riga]
        if intestazione is None:
            if valori and valori[0] == ETICHETTA_GRUPPO and len(valori) > 1:
                lettura.codice_gruppo = valori[1].upper()
            if valori[: len(INTESTAZIONE)] == INTESTAZIONE:
                intestazione = numero
            elif numero >= RIGHE_DA_ESAMINARE:
                break
            continue
        valori += [""] * (len(INTESTAZIONE) - len(valori))
        if not any(valori[: len(INTESTAZIONE)]):
            continue
        lettura.righe.append(
            RigaEmail(
                riga=numero,
                id=valori[0],
                cognome=valori[1],
                nome=valori[2],
                email=valori[4],
            )
        )
    cartella.close()
    if intestazione is None:
        lettura.errore = (
            "Intestazione non trovata: usa il file scaricato da Catello, senza modificarne "
            "le prime righe."
        )
    elif not lettura.codice_gruppo:
        lettura.errore = "Codice gruppo mancante nell'intestazione del file."
    return lettura


# --- Anteprima e conferma ---------------------------------------------------------


@dataclass(frozen=True)
class Anomalia:
    riga: int
    avente: str
    messaggio: str
    bloccante: bool

    def come_dict(self) -> dict:
        return {
            "riga": self.riga,
            "avente": self.avente,
            "messaggio": self.messaggio,
            "bloccante": self.bloccante,
        }


@dataclass
class Modifica:
    avente: AventeDiritto
    vecchia: str
    nuova: str


@dataclass
class AnteprimaEmail:
    gruppo: Gruppo | None = None
    righe_lette: int = 0
    modifiche: list[Modifica] = field(default_factory=list)
    invariate: int = 0
    anomalie: list[Anomalia] = field(default_factory=list)
    errore: str = ""

    @property
    def bloccata(self) -> bool:
        return bool(self.errore) or any(a.bloccante for a in self.anomalie)


def _chiave(testo: str) -> str:
    return " ".join(testo.lower().split())


def anteprima_import(assemblea: Assemblea, lettura: LetturaExcel) -> AnteprimaEmail:
    """Cosa cambierebbe applicando il file: nessuna scrittura. Un'anomalia
    bloccante (riga di un altro gruppo, id sconosciuto o manomesso, email non
    valida) impedisce la conferma dell'intero file."""
    anteprima = AnteprimaEmail(righe_lette=len(lettura.righe))
    if lettura.errore:
        anteprima.errore = lettura.errore
        return anteprima
    anteprima.gruppo = Gruppo.objects.filter(pk=lettura.codice_gruppo).first()
    if anteprima.gruppo is None:
        anteprima.errore = f"Il gruppo {lettura.codice_gruppo} del file non esiste."
        return anteprima
    aventi = {str(a.pk): a for a in assemblea.aventi_diritto.nell_elenco().select_related("capo")}
    visti: set[str] = set()
    for riga in lettura.righe:
        nome = f"{riga.cognome} {riga.nome}".strip()

        def segnala(messaggio: str, bloccante: bool = True, *, riga=riga, nome=nome) -> None:
            anteprima.anomalie.append(Anomalia(riga.riga, nome, messaggio, bloccante))

        avente = aventi.get(riga.id)
        if avente is None:
            segnala("Riga non riconosciuta: l'avente non è nell'elenco di questa assemblea.")
            continue
        if riga.id in visti:
            segnala("Lo stesso avente compare più volte nel file.")
            continue
        visti.add(riga.id)
        if (_chiave(riga.cognome), _chiave(riga.nome)) != (
            _chiave(avente.cognome),
            _chiave(avente.nome),
        ):
            segnala(
                f"Nome e cognome non corrispondono all'avente della riga ({avente}): "
                "la colonna ID è stata modificata o le righe sono state mescolate."
            )
            continue
        if avente.gruppo_id != anteprima.gruppo.pk:
            segnala(f"{avente} non è del gruppo {anteprima.gruppo.nome}.")
            continue
        if not riga.email:
            # Cella vuota: nessuna modifica, l'email non si cancella da qui.
            anteprima.invariate += 1
            continue
        try:
            email = normalizza_email(riga.email)
        except ValidationError:
            segnala(f"Email non valida: «{riga.email}».")
            continue
        if email == avente.email:
            anteprima.invariate += 1
            continue
        anteprima.modifiche.append(Modifica(avente, avente.email, email))
        if avente.capo and avente.capo.email and avente.capo.email.lower() != email:
            segnala(
                "Email diversa da quella dell'anagrafica: per l'assemblea vale quella del file.",
                bloccante=False,
            )
    return anteprima


@transaction.atomic
def applica_import(
    assemblea: Assemblea, contenuto: bytes, nome_file: str, utente: Utente
) -> ImportazioneEmail:
    """Rilegge il file e ricalcola l'anteprima da zero (mai quella mostrata),
    poi aggiorna le email. Idempotente: un secondo import dello stesso file
    non cambia nulla."""
    _verifica_gestore(utente, assemblea)
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa: l'elenco non è più modificabile.")
    anteprima = anteprima_import(assemblea, leggi_excel(contenuto))
    if anteprima.bloccata:
        raise ValidationError(
            anteprima.errore or "Il file ha anomalie bloccanti: correggile e ricaricalo."
        )
    for modifica in anteprima.modifiche:
        modifica.avente.email = modifica.nuova
        modifica.avente.email_corretta = True
        modifica.avente.save(update_fields=["email", "email_corretta"])
    return ImportazioneEmail.objects.create(
        assemblea=assemblea,
        nome_file=nome_file[:255],
        utente=utente,
        righe_lette=anteprima.righe_lette,
        email_aggiornate=len(anteprima.modifiche),
        anomalie=[a.come_dict() for a in anteprima.anomalie],
    )


def report_csv(importazione: ImportazioneEmail) -> str:
    righe = ["riga;avente;bloccante;messaggio"]
    for anomalia in importazione.anomalie:
        campi = [
            str(anomalia["riga"]),
            anomalia["avente"],
            "sì" if anomalia["bloccante"] else "no",
            anomalia["messaggio"],
        ]
        righe.append(";".join('"' + c.replace('"', '""') + '"' for c in campi))
    return "\n".join(righe) + "\n"
