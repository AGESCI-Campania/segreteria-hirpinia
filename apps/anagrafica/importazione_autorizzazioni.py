"""Import PDF di autorizzazione (§6.2, D-08, D-09, D-32, D-34): unico punto
autorizzato a scrivere IncaricoUnita/Pattuglia/Gruppo.data_autorizzazione a
partire dai PDF. View e comando di gestione chiamano solo
`estrai_pdf_da_file_caricati`, `costruisci_piano_autorizzazioni` e
`applica_piano_autorizzazioni`, mai i modelli direttamente."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Utente
from apps.accounts.ruoli_derivati import sincronizza_ruoli_cg
from apps.organizzazione.models import Gruppo

from .derivazioni import ricalcola_derivati_capo, ricalcola_pattuglia
from .models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FileAutorizzazionePDF,
    FunzioneIncarico,
    ImportazioneAutorizzazioni,
    IncaricoUnita,
    OrigineIncarico,
    Pattuglia,
)
from .parser.autorizzazioni import ParseResult, parse_pdf
from .parser.buonacaccia import AVVISO, ERRORE, AnomaliaRiga

# Mappatura totale: _branca() nel parser restituisce solo questi 5 valori
# (verificato leggendo parser/autorizzazioni.py), quindi il fallback su
# SCONOSCIUTA+avviso non dovrebbe mai attivarsi con il parser attuale — resta
# come rete di sicurezza, non come comportamento atteso.
_MAPPATURA_BRANCA_PDF: dict[str, str] = {
    "L/C": BrancaUnita.LC,
    "E/G": BrancaUnita.EG,
    "R/S": BrancaUnita.RS,
    "Adulti": BrancaUnita.ADULTI,
    "SCONOSCIUTA": BrancaUnita.SCONOSCIUTA,
}

# Vocabolario chiuso (D-08): match esatto contro la stringa restituita dal
# parser, mai fuzzy matching. Un valore assente da questo dizionario (incluso
# un caso corrotto) produce un'anomalia e la riga non si scrive.
_MAPPATURA_FUNZIONE_PDF: dict[str, str] = {
    "CAPO UNITÀ": FunzioneIncarico.CAPO_UNITA,
    "AIUTO CAPO UNITÀ": FunzioneIncarico.AIUTO_CAPO_UNITA,
    "CAPO GRUPPO": FunzioneIncarico.CAPO_GRUPPO,
    "ASSISTENTE ECCLESIASTICO DI GRUPPO": FunzioneIncarico.AE_GRUPPO,
    "ASSISTENTE ECCLESIASTICO DI UNITA": FunzioneIncarico.AE_UNITA,
    "SERVIZIO DI SUPPORTO AL GRUPPO": FunzioneIncarico.SUPPORTO_GRUPPO,
    "SERVIZIO DI SUPPORTO ALL'AZIONE EDUCATIVA": FunzioneIncarico.SUPPORTO_AZIONE_EDUCATIVA,
    "MAESTRO DEI NOVIZI": FunzioneIncarico.MAESTRO_NOVIZI,
}


@dataclass(frozen=True)
class PdfCaricato:
    nome_file: str
    contenuto: bytes
    risultato: ParseResult


def _parsa_pdf(
    nome_file: str, contenuto: bytes, anomalie: list[AnomaliaRiga]
) -> PdfCaricato | None:
    """Un file con estensione .pdf che non è un PDF valido (o è illeggibile)
    non deve far fallire l'intero caricamento: produce un'anomalia ERRORE e
    viene escluso, come un ZIP corrotto."""
    try:
        risultato = parse_pdf(io.BytesIO(contenuto))
    except Exception as exc:  # pdfplumber/pdfminer sollevano eccezioni eterogenee
        anomalie.append(
            AnomaliaRiga(0, ERRORE, "File", f"{nome_file}: PDF illeggibile o corrotto ({exc}).", "")
        )
        return None
    return PdfCaricato(nome_file=nome_file, contenuto=contenuto, risultato=risultato)


def estrai_pdf_da_file_caricati(
    file_caricati: list[tuple[str, bytes]],
) -> tuple[list[PdfCaricato], list[AnomaliaRiga]]:
    """Per ogni (nome, contenuto) caricato: se .zip, estrae le voci .pdf
    (case-insensitive); se .pdf, lo parsa direttamente. Le voci non-.pdf in
    uno zip producono un avviso non bloccante; uno zip corrotto o un PDF
    illeggibile producono un errore e vengono saltati senza interrompere gli
    altri file del batch."""
    pdf_caricati: list[PdfCaricato] = []
    anomalie: list[AnomaliaRiga] = []

    for nome, contenuto in file_caricati:
        nome_lower = nome.lower()
        if nome_lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(contenuto)) as archivio:
                    for voce in archivio.infolist():
                        if voce.is_dir():
                            continue
                        if not voce.filename.lower().endswith(".pdf"):
                            anomalie.append(
                                AnomaliaRiga(
                                    0,
                                    AVVISO,
                                    "File",
                                    f"{nome}: voce ignorata (non un PDF): {voce.filename}",
                                    "",
                                )
                            )
                            continue
                        pdf = _parsa_pdf(voce.filename, archivio.read(voce), anomalie)
                        if pdf is not None:
                            pdf_caricati.append(pdf)
            except zipfile.BadZipFile:
                anomalie.append(
                    AnomaliaRiga(
                        0, ERRORE, "File", f"{nome}: archivio ZIP non valido o corrotto.", ""
                    )
                )
        elif nome_lower.endswith(".pdf"):
            pdf = _parsa_pdf(nome, contenuto, anomalie)
            if pdf is not None:
                pdf_caricati.append(pdf)
        else:
            anomalie.append(
                AnomaliaRiga(0, AVVISO, "File", f"{nome}: estensione non ammessa, ignorato.", "")
            )

    return pdf_caricati, anomalie


@dataclass
class OperazioneIncarico:
    codice_socio: str
    anno_scout: int
    gruppo_codice: str
    codice_unita: str
    nome_unita: str
    branca: str
    genere_unita: str
    funzione: str
    livello_foca: int | None
    # Sesso della persona (M/F), da record["genere"] del PDF stesso
    # (parser/autorizzazioni.py::_RE_GENDER) — non Capo.sesso (fonte diversa,
    # dal CSV Buona Caccia): per D-35 si usa il dato legato all'incarico
    # CAPO_GRUPPO stesso. Vuoto se il parser non l'ha riconosciuto.
    genere: str = ""


@dataclass
class PianoAutorizzazioni:
    incarichi: list[OperazioneIncarico] = field(default_factory=list)
    pdf_vincitori: dict[str, PdfCaricato] = field(default_factory=dict)
    anomalie: list[AnomaliaRiga] = field(default_factory=list)
    pdf_processati: int = 0

    @property
    def valido(self) -> bool:
        """True se almeno un PDF caricato è stato riconosciuto come
        autorizzazione di gruppo, anche se poi scartato da D-09."""
        return self.pdf_processati > 0


def costruisci_piano_autorizzazioni(pdf_caricati: list[PdfCaricato]) -> PianoAutorizzazioni:
    """Sola lettura: nessuna scrittura sul database. Applica l'algoritmo D-09:
    ordina per data_aggiornamento crescente, tiene solo il più recente per
    gruppo nel batch, scarta chi ha data_aggiornamento strettamente precedente
    a Gruppo.data_autorizzazione già registrata (stessa data = reimport dello
    stesso snapshot, va sovrascritto). Segnala anche in avviso (non blocca)
    gli incarichi manuali che l'applicazione del piano sostituirebbe (D-32)."""
    anomalie: list[AnomaliaRiga] = [
        AnomaliaRiga(
            0,
            ERRORE,
            "File",
            f"{p.nome_file}: PDF non riconosciuto come autorizzazione di gruppo.",
            "",
        )
        for p in pdf_caricati
        if not p.risultato.is_valido
    ]

    validi = [p for p in pdf_caricati if p.risultato.is_valido]

    per_gruppo: dict[str, PdfCaricato] = {}
    for p in sorted(validi, key=lambda p: p.risultato.data_aggiornamento):
        per_gruppo[p.risultato.gruppo_codice] = p

    gruppi_esistenti = {g.codice: g for g in Gruppo.objects.filter(codice__in=per_gruppo.keys())}

    pdf_vincitori: dict[str, PdfCaricato] = {}
    for codice, pdf in per_gruppo.items():
        gruppo = gruppi_esistenti.get(codice)
        if gruppo is None:
            anomalie.append(
                AnomaliaRiga(
                    0,
                    ERRORE,
                    "Gruppo",
                    f"{pdf.nome_file}: il gruppo {codice} non esiste in anagrafica.",
                    "",
                )
            )
            continue

        nuova = pdf.risultato.data_aggiornamento.date()
        registrata = gruppo.data_autorizzazione
        if registrata is not None and nuova < registrata:
            anomalie.append(
                AnomaliaRiga(
                    0,
                    ERRORE,
                    "Autorizzazione",
                    f"{pdf.nome_file}: data aggiornamento {nuova:%d/%m/%Y} precedente "
                    f"all'ultima registrata per {codice} ({registrata:%d/%m/%Y}). Scartato (D-09).",
                    "",
                )
            )
            continue

        pdf_vincitori[codice] = pdf

    codici_socio_nei_pdf = {
        record["codice_socio"] for pdf in pdf_vincitori.values() for record in pdf.risultato.records
    }
    codici_esistenti = set(
        Capo.objects.filter(codice_socio__in=codici_socio_nei_pdf).values_list(
            "codice_socio", flat=True
        )
    )

    incarichi: list[OperazioneIncarico] = []
    for codice, pdf in pdf_vincitori.items():
        for record in pdf.risultato.records:
            branca = _MAPPATURA_BRANCA_PDF.get(record["branca"])
            if branca is None:
                anomalie.append(
                    AnomaliaRiga(
                        0,
                        AVVISO,
                        "Branca",
                        f"Branca unità non riconosciuta: {record['branca']!r}.",
                        record["codice_socio"],
                    )
                )
                branca = BrancaUnita.SCONOSCIUTA

            funzione = _MAPPATURA_FUNZIONE_PDF.get(record["funzione"])
            if funzione is None:
                anomalie.append(
                    AnomaliaRiga(
                        0,
                        ERRORE,
                        "Funzione",
                        f"Funzione non nel vocabolario chiuso: {record['funzione']!r}. Riga non importata (D-08).",
                        record["codice_socio"],
                    )
                )
                continue

            if record["codice_socio"] not in codici_esistenti:
                anomalie.append(
                    AnomaliaRiga(
                        0,
                        ERRORE,
                        "Capo",
                        f"Codice socio {record['codice_socio']} assente in anagrafica: incarico non creato (D-34).",
                        record["codice_socio"],
                    )
                )
                continue

            codice_unita, _sep, nome_unita = record["unita"].partition(" ")
            incarichi.append(
                OperazioneIncarico(
                    codice_socio=record["codice_socio"],
                    anno_scout=record["anno"],
                    gruppo_codice=codice,
                    codice_unita=codice_unita,
                    nome_unita=nome_unita,
                    branca=branca,
                    genere_unita=record["genere_unita"],
                    funzione=funzione,
                    livello_foca=record["livello_foca"] or None,
                    genere=record["genere"],
                )
            )

    anomalie.extend(_anomalie_incarichi_manuali_sovrascritti(incarichi))

    return PianoAutorizzazioni(
        incarichi=incarichi,
        pdf_vincitori=pdf_vincitori,
        anomalie=anomalie,
        pdf_processati=len(validi),
    )


def _anomalie_incarichi_manuali_sovrascritti(
    incarichi: list[OperazioneIncarico],
) -> list[AnomaliaRiga]:
    """D-32: l'import sostituisce sempre gli incarichi manuali del gruppo/anno
    toccati (non si scrive logica che li preservi), ma la sostituzione va resa
    visibile in anteprima con un avviso, non applicata in silenzio: la
    conferma esplicita del flusso a due fasi è la conferma di sovrascrittura."""
    anno_per_gruppo: dict[str, set[int]] = {}
    for op in incarichi:
        anno_per_gruppo.setdefault(op.gruppo_codice, set()).add(op.anno_scout)

    if not anno_per_gruppo:
        return []

    coppie = Q()
    for gruppo_codice, anni in anno_per_gruppo.items():
        coppie |= Q(gruppo_servizio_id=gruppo_codice, anno_scout__in=anni)

    manuali_sovrascritti = IncaricoUnita.objects.filter(
        coppie, origine=OrigineIncarico.MANUALE, cessato_il__isnull=True
    )

    return [
        AnomaliaRiga(
            0,
            AVVISO,
            "Incarico manuale",
            f"{incarico.capo_id} — {incarico.get_funzione_display()} in "
            f"{incarico.codice_unita} {incarico.nome_unita} ({incarico.gruppo_servizio_id}, "
            f"{incarico.anno_scout}): incarico assegnato manualmente, verrà sostituito "
            "dall'autorizzazione importata (D-32). Conferma per procedere.",
            incarico.capo_id,
        )
        for incarico in manuali_sovrascritti.order_by("capo_id")
    ]


def applica_piano_autorizzazioni(
    piano: PianoAutorizzazioni, *, utente: Utente | None
) -> ImportazioneAutorizzazioni:
    """Scrive tutto dentro un'unica transazione: sostituzione integrale degli
    incarichi per (gruppo, anno) toccati (D-32), ricalcolo dei derivati e
    delle pattuglie, sincronizzazione del ruolo CG (D-30)."""
    if not piano.valido:
        raise ValueError(
            "Piano non applicabile: nessun PDF di autorizzazione riconosciuto nel caricamento."
        )

    with transaction.atomic():
        anomalie = list(piano.anomalie)
        conteggi = {
            "pdf_caricati": piano.pdf_processati,
            "gruppi_applicati": 0,
            "incarichi_creati": 0,
            "capi_impattati": 0,
        }

        anno_per_gruppo: dict[str, set[int]] = {}
        for op in piano.incarichi:
            anno_per_gruppo.setdefault(op.gruppo_codice, set()).add(op.anno_scout)

        ora = timezone.now()
        capi_impattati: set[tuple[str, int]] = set()

        for gruppo_codice, anni in anno_per_gruppo.items():
            for anno in anni:
                attivi_prima = IncaricoUnita.objects.filter(
                    gruppo_servizio_id=gruppo_codice, anno_scout=anno, cessato_il__isnull=True
                )
                capi_impattati |= {
                    (c, anno) for c in attivi_prima.values_list("capo_id", flat=True)
                }
                attivi_prima.update(cessato_il=ora)

        # D-35: due CG attivi dello stesso sesso sullo stesso gruppo/anno non
        # sono rappresentabili nel dominio — unica eccezione bloccante allo
        # stile generale di import (anomalie non bloccanti). Il sesso viene dal
        # PDF stesso (op.genere), non da Capo.sesso (fonte diversa, CSV): un
        # sesso ignoto (regex non riconosciuta) non partecipa al blocco, solo
        # all'anomalia finale sul conteggio dei CG.
        genere_per_capo: dict[str, str] = {
            op.codice_socio: op.genere
            for op in piano.incarichi
            if op.funzione == FunzioneIncarico.CAPO_GRUPPO
        }
        cg_attivi_per_gruppo: dict[tuple[str, int], list[str]] = {}

        for op in piano.incarichi:
            if op.funzione == FunzioneIncarico.CAPO_GRUPPO:
                chiave = (op.gruppo_codice, op.anno_scout)
                sesso = op.genere
                if sesso:
                    conflitto = next(
                        (
                            c
                            for c in cg_attivi_per_gruppo.get(chiave, [])
                            if genere_per_capo.get(c) == sesso
                        ),
                        None,
                    )
                    if conflitto is not None:
                        anomalie.append(
                            AnomaliaRiga(
                                0,
                                ERRORE,
                                "CapoGruppo",
                                f"{op.codice_socio}: stesso sesso di {conflitto}, già "
                                f"capogruppo attivo di {op.gruppo_codice} (D-35). "
                                "Incarico non creato.",
                                op.codice_socio,
                            )
                        )
                        continue

            incarico = IncaricoUnita(
                capo_id=op.codice_socio,
                anno_scout=op.anno_scout,
                gruppo_servizio_id=op.gruppo_codice,
                codice_unita=op.codice_unita,
                nome_unita=op.nome_unita,
                branca=op.branca,
                genere_unita=op.genere_unita,
                funzione=op.funzione,
                livello_foca=op.livello_foca,
                origine=OrigineIncarico.IMPORT,
            )
            try:
                with transaction.atomic():
                    incarico.full_clean()
                    incarico.save()
            except ValidationError as exc:
                anomalie.append(AnomaliaRiga(0, ERRORE, "IncaricoUnita", str(exc), op.codice_socio))
                continue
            capi_impattati.add((op.codice_socio, op.anno_scout))
            conteggi["incarichi_creati"] += 1
            if op.funzione == FunzioneIncarico.CAPO_GRUPPO:
                cg_attivi_per_gruppo.setdefault((op.gruppo_codice, op.anno_scout), []).append(
                    op.codice_socio
                )

        for (gruppo_codice, anno), codici in cg_attivi_per_gruppo.items():
            if len(codici) == 1:
                anomalie.append(
                    AnomaliaRiga(
                        0,
                        AVVISO,
                        "CapoGruppo",
                        f"{gruppo_codice} ({anno}): un solo capogruppo attivo "
                        f"({codici[0]}), posto vacante (D-35).",
                        codici[0],
                    )
                )
            livelli = dict(
                CensimentoCapo.objects.filter(capo_id__in=codici, anno_scout=anno).values_list(
                    "capo_id", "livello_foca"
                )
            )
            for codice_socio in codici:
                if livelli.get(codice_socio) != 5:
                    anomalie.append(
                        AnomaliaRiga(
                            0,
                            AVVISO,
                            "CapoGruppo",
                            f"{codice_socio}: capogruppo di {gruppo_codice} ({anno}) con "
                            f"Livello Fo.Ca. {livelli.get(codice_socio) or 'assente'}, "
                            "diverso da 5 (D-35).",
                            codice_socio,
                        )
                    )

        capi_map = {
            c.codice_socio: c
            for c in Capo.objects.filter(
                codice_socio__in={capo_id for capo_id, _anno in capi_impattati}
            ).select_related("utente")
        }

        for capo_id, anno in capi_impattati:
            censimento = ricalcola_derivati_capo(capo_id, anno)
            if censimento is None:
                anomalie.append(
                    AnomaliaRiga(
                        0,
                        AVVISO,
                        "CensimentoCapo",
                        f"Capo {capo_id} non censito nell'anno {anno}: derivati non aggiornati.",
                        capo_id,
                    )
                )
                continue

            gruppi_capogruppo = frozenset(
                IncaricoUnita.objects.filter(
                    capo_id=capo_id,
                    anno_scout=anno,
                    funzione=FunzioneIncarico.CAPO_GRUPPO,
                    cessato_il__isnull=True,
                ).values_list("gruppo_servizio_id", flat=True)
            )
            if len(gruppi_capogruppo) > 1:
                # D-35: un solo gruppo reale per CG — anomalia non bloccante,
                # mai una scelta arbitraria di quale tenere. Vale anche per i
                # capi senza account: è un fatto sull'incarico, non sul ruolo.
                anomalie.append(
                    AnomaliaRiga(
                        0,
                        AVVISO,
                        "CapoGruppo",
                        f"{capo_id}: capogruppo attivo su più gruppi reali "
                        f"contemporaneamente ({', '.join(sorted(gruppi_capogruppo))}), "
                        "atteso un solo gruppo (D-35).",
                        capo_id,
                    )
                )

            capo = capi_map.get(capo_id)
            if capo is not None and capo.utente_id:
                sincronizza_ruoli_cg(
                    utente=capo.utente, gruppi_capogruppo=gruppi_capogruppo, assegnato_da=utente
                )

        anni_impattati = {anno for _capo_id, anno in capi_impattati}
        for anno in anni_impattati:
            for branca in Pattuglia.BRANCHE_AMMESSE:
                ricalcola_pattuglia(branca, anno)

        for codice in piano.pdf_vincitori:
            Gruppo.objects.filter(codice=codice).update(
                data_autorizzazione=piano.pdf_vincitori[codice].risultato.data_aggiornamento.date()
            )

        conteggi["gruppi_applicati"] = len(piano.pdf_vincitori)
        conteggi["capi_impattati"] = len(capi_impattati)
        conteggi["anomalie_bloccanti"] = sum(1 for a in anomalie if a.livello == ERRORE)
        conteggi["avvisi"] = sum(1 for a in anomalie if a.livello == AVVISO)

        anni_pdf = {pdf.risultato.anno for pdf in piano.pdf_vincitori.values()}
        importazione = ImportazioneAutorizzazioni(
            anno_scout=max(anni_pdf) if anni_pdf else 0,
            conteggi=conteggi,
            anomalie=[_anomalia_a_dict(a) for a in anomalie],
            utente=utente,
        )
        importazione.save()

        for codice, pdf in piano.pdf_vincitori.items():
            FileAutorizzazionePDF.objects.create(
                importazione=importazione,
                file=ContentFile(pdf.contenuto, name=pdf.nome_file),
                nome_file_originale=pdf.nome_file,
                gruppo_id=codice,
                data_aggiornamento=pdf.risultato.data_aggiornamento.date(),
            )

    return importazione


def _anomalia_a_dict(a: AnomaliaRiga) -> dict:
    return {
        "numero_riga": a.numero_riga,
        "livello": a.livello,
        "campo": a.campo,
        "dettaglio": a.dettaglio,
        "codice_socio": a.codice_socio,
    }
