"""Viste dell'import CSV Buona Caccia (§6.1) e dell'import PDF di
autorizzazione (§6.2): due fasi, anteprima e conferma, mai una scrittura sul
database prima della conferma esplicita (CLAUDE.md)."""

import base64
import csv
import io
import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView
from openpyxl import Workbook

from apps.accounts.mixins import RuoloRequiredMixin
from apps.accounts.permessi import gruppi_visibili
from apps.organizzazione.models import anno_scout_corrente

from .esportazione import (
    RUOLI_EXPORT_ANAGRAFICA,
    RUOLI_VISUALIZZAZIONE_ESPORTAZIONI,
    FiltriEsportazione,
    RigaEsportazione,
    colonne_per_profilo,
    etichetta_unita,
    genera_righe_esportazione,
    ordina_per_raggruppamento,
    raggruppa_righe,
)
from .forms import (
    EsportazioneAnagraficaForm,
    ImportazioneAutorizzazioniForm,
    ImportazioneCSVForm,
    IncaricoManualeForm,
    RicercaCapoForm,
)
from .importazione import (
    RUOLI_IMPORT_ANAGRAFICA,
    applica_piano,
    costruisci_piano,
    ultima_importazione_completata,
)
from .importazione_autorizzazioni import (
    applica_piano_autorizzazioni,
    costruisci_piano_autorizzazioni,
    estrai_pdf_da_file_caricati,
)
from .incarichi import (
    RUOLI_ASSEGNAZIONE_INCARICHI,
    RUOLI_RICERCA_CAPO,
    assegna_incarico_manuale,
    cerca_capo_per_codice_socio,
    cessa_incarico_manuale,
)
from .models import (
    CensimentoCapo,
    EsportazioneAnagrafica,
    ImportazioneAutorizzazioni,
    ImportazioneCSV,
    IncaricoUnita,
)
from .parser.buonacaccia import parse_csv

_SESSION_TESTO = "anagrafica_import_csv_testo"
_SESSION_NOME_FILE = "anagrafica_import_csv_nome_file"
_SESSION_UTENTE_ID = "anagrafica_import_csv_utente_id"


class ImportazioneAnteprimaView(RuoloRequiredMixin, View):
    """L'anteprima non scrive nulla: il file caricato si legge solo in
    memoria e il testo decodificato si tiene in sessione (DB-backed) per la
    conferma, mai su disco (D-17: niente pulizia differita via Celery)."""

    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA
    template_name = "anagrafica/importazione_anteprima.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ImportazioneCSVForm()})

    def post(self, request):
        form = ImportazioneCSVForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        file = form.cleaned_data["file"]
        testo = file.read().decode("utf-8-sig")
        risultato = parse_csv(io.StringIO(testo))
        piano = costruisci_piano(risultato)

        if not piano.valido:
            dettaglio = "; ".join(risultato.anomalie_file) or "file non riconosciuto."
            form.add_error("file", f"Impossibile determinare l'anno scout dal file: {dettaglio}")
            return render(request, self.template_name, {"form": form})

        request.session[_SESSION_TESTO] = testo
        request.session[_SESSION_NOME_FILE] = file.name
        request.session[_SESSION_UTENTE_ID] = request.user.pk

        contesto = {
            "piano": piano,
            "ultima_importazione": ultima_importazione_completata(piano.anno_scout),
        }
        return render(request, self.template_name, contesto)


class ImportazioneConfermaView(RuoloRequiredMixin, View):
    """POST-only: rilegge il CSV dalla sessione e ricalcola il piano da zero
    (mai riusa quello dell'anteprima), poi scrive tutto dentro
    `applica_piano()`. Anteprima e conferma devono avvenire nella stessa
    sessione utente."""

    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA

    def post(self, request):
        testo = request.session.get(_SESSION_TESTO)
        utente_id = request.session.get(_SESSION_UTENTE_ID)
        if not testo or utente_id != request.user.pk:
            messages.error(
                request,
                "L'anteprima è scaduta o non è più valida: ripeti il caricamento del file.",
            )
            return redirect("anagrafica:importazione_anteprima")

        risultato = parse_csv(io.StringIO(testo))
        piano = costruisci_piano(risultato)
        if not piano.valido:
            messages.error(request, "Il file non è più valido: ripeti il caricamento.")
            return redirect("anagrafica:importazione_anteprima")

        nome_file = request.session.get(_SESSION_NOME_FILE) or "ricercasoci.csv"
        file_originale = ContentFile(testo.encode("utf-8-sig"), name=nome_file)
        importazione = applica_piano(piano, file_originale=file_originale, utente=request.user)

        for chiave in (_SESSION_TESTO, _SESSION_NOME_FILE, _SESSION_UTENTE_ID):
            request.session.pop(chiave, None)

        messages.success(request, "Importazione completata.")
        return redirect(reverse("anagrafica:importazione_dettaglio", args=[importazione.pk]))


class ImportazioneListaView(RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA
    template_name = "anagrafica/importazione_lista.html"
    context_object_name = "importazioni"
    paginate_by = 50

    def get_queryset(self):
        return ImportazioneCSV.objects.select_related("utente")


class ImportazioneDettaglioView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA
    template_name = "anagrafica/importazione_dettaglio.html"

    def get(self, request, pk):
        importazione = ImportazioneCSV.objects.select_related("utente").get(pk=pk)
        return render(request, self.template_name, {"importazione": importazione})


class ImportazioneReportCSVView(RuoloRequiredMixin, View):
    """Streaming del report generato al volo da ImportazioneCSV, mai un link
    diretto a `file.url` (nessuna `MEDIA_URL` pubblica per questi file)."""

    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA

    def get(self, request, pk):
        importazione = ImportazioneCSV.objects.get(pk=pk)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="importazione_{importazione.pk}_report.csv"'
        )
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Conteggio", "Valore"])
        for chiave, valore in importazione.conteggi.items():
            writer.writerow([chiave, valore])
        writer.writerow([])
        writer.writerow(["Riga", "Livello", "Campo", "Dettaglio", "Codice socio"])
        for anomalia in importazione.anomalie:
            writer.writerow(
                [
                    anomalia.get("numero_riga"),
                    anomalia.get("livello"),
                    anomalia.get("campo"),
                    anomalia.get("dettaglio"),
                    anomalia.get("codice_socio"),
                ]
            )
        return response


# ── Import PDF di autorizzazione (§6.2, M3) ─────────────────────────────────

_SESSION_PDF_FILES = "anagrafica_import_pdf_files"
_SESSION_PDF_UTENTE_ID = "anagrafica_import_pdf_utente_id"


class ImportazioneAutorizzazioniAnteprimaView(RuoloRequiredMixin, View):
    """L'anteprima non scrive nulla: i PDF/ZIP caricati si leggono solo in
    memoria e i bytes originali si tengono in sessione (DB-backed, base64) per
    la conferma, mai su disco (D-17)."""

    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA
    template_name = "anagrafica/importazione_autorizzazioni_anteprima.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ImportazioneAutorizzazioniForm()})

    def post(self, request):
        form = ImportazioneAutorizzazioniForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        file_caricati = [(f.name, f.read()) for f in form.cleaned_data["file"]]
        pdf_caricati, anomalie_estrazione = estrai_pdf_da_file_caricati(file_caricati)
        piano = costruisci_piano_autorizzazioni(pdf_caricati)
        piano.anomalie = anomalie_estrazione + piano.anomalie

        if not piano.valido:
            dettaglio = "; ".join(a.dettaglio for a in piano.anomalie) or "nessun PDF riconosciuto."
            form.add_error("file", f"Impossibile elaborare il caricamento: {dettaglio}")
            return render(request, self.template_name, {"form": form})

        request.session[_SESSION_PDF_FILES] = [
            {"nome": nome, "b64": base64.b64encode(contenuto).decode("ascii")}
            for nome, contenuto in file_caricati
        ]
        request.session[_SESSION_PDF_UTENTE_ID] = request.user.pk

        return render(request, self.template_name, {"piano": piano})


class ImportazioneAutorizzazioniConfermaView(RuoloRequiredMixin, View):
    """POST-only: rilegge i file dalla sessione e ricalcola il piano da zero
    (mai riusa quello dell'anteprima), poi applica."""

    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA

    def post(self, request):
        file_sessione = request.session.get(_SESSION_PDF_FILES)
        utente_id = request.session.get(_SESSION_PDF_UTENTE_ID)
        if not file_sessione or utente_id != request.user.pk:
            messages.error(
                request,
                "L'anteprima è scaduta o non è più valida: ripeti il caricamento dei file.",
            )
            return redirect("anagrafica:importazione_autorizzazioni_anteprima")

        file_caricati = [(voce["nome"], base64.b64decode(voce["b64"])) for voce in file_sessione]
        pdf_caricati, anomalie_estrazione = estrai_pdf_da_file_caricati(file_caricati)
        piano = costruisci_piano_autorizzazioni(pdf_caricati)
        piano.anomalie = anomalie_estrazione + piano.anomalie

        if not piano.valido:
            messages.error(request, "Il caricamento non è più valido: ripeti l'operazione.")
            return redirect("anagrafica:importazione_autorizzazioni_anteprima")

        importazione = applica_piano_autorizzazioni(piano, utente=request.user)

        for chiave in (_SESSION_PDF_FILES, _SESSION_PDF_UTENTE_ID):
            request.session.pop(chiave, None)

        messages.success(request, "Importazione autorizzazioni completata.")
        return redirect(
            reverse("anagrafica:importazione_autorizzazioni_dettaglio", args=[importazione.pk])
        )


class ImportazioneAutorizzazioniListaView(RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA
    template_name = "anagrafica/importazione_autorizzazioni_lista.html"
    context_object_name = "importazioni"
    paginate_by = 50

    def get_queryset(self):
        return ImportazioneAutorizzazioni.objects.select_related("utente")


class ImportazioneAutorizzazioniDettaglioView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA
    template_name = "anagrafica/importazione_autorizzazioni_dettaglio.html"

    def get(self, request, pk):
        importazione = get_object_or_404(
            ImportazioneAutorizzazioni.objects.select_related("utente").prefetch_related(
                "file_pdf"
            ),
            pk=pk,
        )
        return render(request, self.template_name, {"importazione": importazione})


class ImportazioneAutorizzazioniReportCSVView(RuoloRequiredMixin, View):
    """Streaming del report generato al volo, mai un link diretto a `file.url`."""

    ruoli_ammessi = RUOLI_IMPORT_ANAGRAFICA

    def get(self, request, pk):
        importazione = get_object_or_404(ImportazioneAutorizzazioni, pk=pk)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="importazione_autorizzazioni_{importazione.pk}_report.csv"'
        )
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Conteggio", "Valore"])
        for chiave, valore in importazione.conteggi.items():
            writer.writerow([chiave, valore])
        writer.writerow([])
        writer.writerow(["Riga", "Livello", "Campo", "Dettaglio", "Codice socio"])
        for anomalia in importazione.anomalie:
            writer.writerow(
                [
                    anomalia.get("numero_riga"),
                    anomalia.get("livello"),
                    anomalia.get("campo"),
                    anomalia.get("dettaglio"),
                    anomalia.get("codice_socio"),
                ]
            )
        return response


# ── Assegnazione manuale degli incarichi (M3b) ──────────────────────────────


class RicercaCapoView(RuoloRequiredMixin, View):
    """Ricerca per codice socio esatto (D-34): riservata a chi ha perimetro
    di Zona. Deciso con l'utente: D-32 vale alla lettera, un account di
    gruppo (CG) non cerca capi censiti altrove."""

    ruoli_ammessi = RUOLI_RICERCA_CAPO
    template_name = "anagrafica/ricerca_capo.html"

    def get(self, request):
        form = RicercaCapoForm(request.GET or None)
        trovato = None
        cercato = False
        if form.is_valid():
            cercato = True
            trovato = cerca_capo_per_codice_socio(
                form.cleaned_data["codice_socio"], anno_scout=anno_scout_corrente()
            )
        return render(
            request, self.template_name, {"form": form, "trovato": trovato, "cercato": cercato}
        )


class AssegnaIncaricoView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_ASSEGNAZIONE_INCARICHI
    template_name = "anagrafica/assegna_incarico.html"

    def get(self, request):
        anno = anno_scout_corrente()
        codice_socio = request.GET.get("codice_socio", "")
        gruppi = gruppi_visibili(request.user, anno)
        form = IncaricoManualeForm(
            initial={"codice_socio": codice_socio, "anno_scout": anno}, gruppi_queryset=gruppi
        )
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        anno = anno_scout_corrente()
        gruppi = gruppi_visibili(request.user, anno)
        form = IncaricoManualeForm(request.POST, gruppi_queryset=gruppi)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        dati = form.cleaned_data
        try:
            incarico = assegna_incarico_manuale(
                utente=request.user,
                codice_socio=dati["codice_socio"],
                anno_scout=dati["anno_scout"],
                gruppo_servizio=dati["gruppo_servizio"],
                codice_unita=dati["codice_unita"],
                nome_unita=dati["nome_unita"],
                branca=dati["branca"],
                genere_unita=dati["genere_unita"],
                funzione=dati["funzione"],
                livello_foca=dati["livello_foca"],
            )
        except PermissionDenied as exc:
            form.add_error(None, str(exc))
            return render(request, self.template_name, {"form": form})
        except ValidationError as exc:
            messaggio = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            form.add_error(None, messaggio)
            return render(request, self.template_name, {"form": form})

        messages.success(request, "Incarico assegnato.")
        return redirect("anagrafica:capo_incarichi", codice_socio=incarico.capo_id)


class CessaIncaricoView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_ASSEGNAZIONE_INCARICHI

    def post(self, request, pk):
        incarico = get_object_or_404(IncaricoUnita, pk=pk)
        try:
            cessa_incarico_manuale(utente=request.user, incarico=incarico)
        except PermissionDenied as exc:
            messages.error(request, str(exc))
        except ValidationError as exc:
            messages.error(
                request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            )
        else:
            messages.success(request, "Incarico cessato.")
        return redirect("anagrafica:capo_incarichi", codice_socio=incarico.capo_id)


class CapoIncarichiView(RuoloRequiredMixin, View):
    """Elenco degli incarichi (attivi e cessati) di un capo per l'anno
    corrente: punto di atterraggio dopo assegnazione/cessazione."""

    ruoli_ammessi = RUOLI_ASSEGNAZIONE_INCARICHI
    template_name = "anagrafica/capo_incarichi.html"

    def get(self, request, codice_socio):
        anno = anno_scout_corrente()
        incarichi = (
            IncaricoUnita.objects.filter(capo_id=codice_socio, anno_scout=anno)
            .select_related("gruppo_servizio")
            .order_by("-cessato_il", "codice_unita")
        )
        return render(
            request,
            self.template_name,
            {"codice_socio": codice_socio, "anno_scout": anno, "incarichi": incarichi},
        )


# ── Export anagrafica (M8, D-23) ────────────────────────────────────────────


def _filtri_da_dati(dati: dict) -> FiltriEsportazione:
    return FiltriEsportazione(
        anno_scout=dati["anno_scout"],
        gruppo=dati["gruppo"],
        unita=dati["unita"],
        funzione=dati["funzione"],
        livello_foca=dati["livello_foca"],
        stato=dati["stato"],
        raggruppamento=dati["raggruppamento"],
        profilo_colonne=dati["profilo_colonne"],
    )


def _scelte_form_esportazione(utente) -> dict:
    """Valori attivi (gruppo) o presenti nelle anagrafiche (unità, livello
    Fo.Ca.) per popolare le select di EsportazioneAnagraficaForm, invece di
    lasciarli come campi di testo libero."""
    gruppi = gruppi_visibili(utente, anno_scout_corrente())
    nomi_unita: dict[str, str] = {}
    for codice, nome in (
        IncaricoUnita.objects.exclude(codice_unita="")
        .values_list("codice_unita", "nome_unita")
        .distinct()
        .order_by("codice_unita")
    ):
        nomi_unita.setdefault(codice, nome)
    livelli_foca = (
        CensimentoCapo.objects.exclude(livello_foca__isnull=True)
        .values_list("livello_foca", flat=True)
        .distinct()
        .order_by("livello_foca")
    )
    return {
        "gruppi_choices": [(g.codice, f"{g.nome} ({g.codice})") for g in gruppi.order_by("nome")],
        "unita_choices": [
            (codice, etichetta_unita(codice, nome)) for codice, nome in sorted(nomi_unita.items())
        ],
        "livello_foca_choices": [(str(livello), str(livello)) for livello in livelli_foca],
    }


class EsportazioneAnagraficaView(RuoloRequiredMixin, View):
    """D-23: la ricerca (GET, senza effetti collaterali, bookmarkabile) mostra
    l'elenco dei capi che rispettano i filtri come tabella; l'esportazione
    vera e propria (POST, tracciata in EsportazioneAnagrafica) genera e
    scarica subito il file con **gli stessi filtri** già mostrati in
    tabella — mai una ricerca separata da quella che poi si esporta."""

    ruoli_ammessi = RUOLI_EXPORT_ANAGRAFICA
    template_name = "anagrafica/esportazione_form.html"

    def get(self, request):
        form = EsportazioneAnagraficaForm(
            request.GET or None,
            initial={"anno_scout": anno_scout_corrente()},
            **_scelte_form_esportazione(request.user),
        )
        contesto = {"form": form}
        if request.GET and form.is_valid():
            filtri = _filtri_da_dati(form.cleaned_data)
            try:
                righe = genera_righe_esportazione(request.user, filtri)
            except PermissionDenied as exc:
                form.add_error("gruppo", str(exc))
            else:
                colonne = colonne_per_profilo(filtri.profilo_colonne)
                righe_ordinate = ordina_per_raggruppamento(righe, filtri.raggruppamento)
                contesto["intestazioni"] = [etichetta for etichetta, _ in colonne]
                contesto["righe_tabella"] = _righe_colonne(righe_ordinate, colonne)
                contesto["numero_capi"] = len({r.codice_socio for r in righe})
        return render(request, self.template_name, contesto)

    def post(self, request):
        form = EsportazioneAnagraficaForm(request.POST, **_scelte_form_esportazione(request.user))
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        dati = form.cleaned_data
        formato = dati.get("formato") or "csv"
        filtri = _filtri_da_dati(dati)
        try:
            righe = genera_righe_esportazione(request.user, filtri)
        except PermissionDenied as exc:
            form.add_error("gruppo", str(exc))
            return render(request, self.template_name, {"form": form})

        EsportazioneAnagrafica.objects.create(
            utente=request.user,
            anno_scout=filtri.anno_scout,
            filtri={
                "gruppo": filtri.gruppo,
                "unita": filtri.unita,
                "funzione": filtri.funzione,
                "livello_foca": filtri.livello_foca,
                "stato": filtri.stato,
                "raggruppamento": filtri.raggruppamento,
                "formato": formato,
            },
            profilo_colonne=filtri.profilo_colonne,
            numero_righe=len(righe),
            numero_capi=len({r.codice_socio for r in righe}),
        )

        colonne = colonne_per_profilo(filtri.profilo_colonne)
        if formato == "xlsx":
            return _esportazione_xlsx(righe, colonne, filtri.raggruppamento, filtri.anno_scout)
        return _esportazione_csv(righe, colonne, filtri.raggruppamento, filtri.anno_scout)


class EsportazioneAnagraficaListaView(RuoloRequiredMixin, ListView):
    """Registro delle esportazioni, visibile solo ad ADMIN (D-23)."""

    ruoli_ammessi = RUOLI_VISUALIZZAZIONE_ESPORTAZIONI
    template_name = "anagrafica/esportazione_lista.html"
    context_object_name = "esportazioni"
    paginate_by = 50

    def get_queryset(self):
        return EsportazioneAnagrafica.objects.select_related("utente")


def _righe_colonne(righe: list[RigaEsportazione], colonne) -> list[list]:
    return [[getter(riga) for _, getter in colonne] for riga in righe]


def _esportazione_csv(righe, colonne, raggruppamento: str, anno_scout: int) -> HttpResponse:
    righe_ordinate = ordina_per_raggruppamento(righe, raggruppamento)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="anagrafica_{anno_scout}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([etichetta for etichetta, _ in colonne])
    for valori in _righe_colonne(righe_ordinate, colonne):
        writer.writerow(valori)
    return response


def _nome_foglio(etichetta: str) -> str:
    # Excel: massimo 31 caratteri, niente : \ / ? * [ ]
    pulito = re.sub(r"[:\\/?*\[\]]", "", etichetta).strip()
    return (pulito or "Capi")[:31]


def _esportazione_xlsx(righe, colonne, raggruppamento: str, anno_scout: int) -> HttpResponse:
    gruppi = raggruppa_righe(righe, raggruppamento)
    cartella = Workbook()
    cartella.remove(cartella.active)
    for etichetta, righe_gruppo in gruppi.items():
        foglio = cartella.create_sheet(_nome_foglio(etichetta))
        foglio.append([intestazione for intestazione, _ in colonne])
        for valori in _righe_colonne(righe_gruppo, colonne):
            foglio.append(valori)
    buffer = io.BytesIO()
    cartella.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="anagrafica_{anno_scout}.xlsx"'
    return response
