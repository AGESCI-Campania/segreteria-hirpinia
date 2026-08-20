"""Viste dell'import CSV Buona Caccia (§6.1): due fasi, anteprima e conferma,
mai una scrittura sul database prima della conferma esplicita (CLAUDE.md)."""

import csv
import io

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.accounts.mixins import RuoloRequiredMixin

from .forms import ImportazioneCSVForm
from .importazione import (
    RUOLI_IMPORT_ANAGRAFICA,
    applica_piano,
    costruisci_piano,
    ultima_importazione_completata,
)
from .models import ImportazioneCSV
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
