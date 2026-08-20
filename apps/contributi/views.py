"""Viste di `contributi`: apertura campagna, inserimento manuale, caricamento
massivo a due fasi (D-21) — stesso schema anteprima/conferma già in uso in
`apps/anagrafica/views.py` (mai una scrittura prima della conferma esplicita,
CLAUDE.md)."""

import base64
import csv
import io

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
from apps.core.models import ImpostazioniPiattaforma

from .bonifici import RigaBonifico, genera_righe_bonifici
from .campagne import (
    RUOLI_GESTIONE_CAMPAGNA,
    apri_campagna,
    avvia_valutazione,
    chiudi_campagna,
    liquida_campagna,
)
from .forms import (
    AllegatoPartecipazioneForm,
    BonificiGeneraForm,
    CampagnaForm,
    ImportazionePartecipazioniForm,
    LiquidaCampagnaForm,
    PartecipazioneManualeForm,
    RespingiPartecipazioneForm,
)
from .importazione_partecipazioni import (
    COLONNE_TRACCIATO,
    applica_piano_partecipazioni,
    costruisci_piano_partecipazioni,
    leggi_righe_csv,
    leggi_righe_xlsx,
)
from .inserimento import RUOLI_GESTIONE_PARTECIPAZIONI, inserisci_partecipazione_manuale
from .models import Campagna, ImportazionePartecipazioni, Partecipazione
from .simulazione import simula_calcolo
from .valutazione import (
    RUOLI_VALUTAZIONE_PARTECIPAZIONI,
    approva_partecipazione,
    carica_allegato,
    respingi_partecipazione,
    richiedi_documenti,
)
from .visibilita import partecipazioni_visibili

_SESSION_FILE_B64 = "contributi_import_file_b64"
_SESSION_NOME_FILE = "contributi_import_nome_file"
_SESSION_CAMPAGNA_ID = "contributi_import_campagna_id"
_SESSION_UTENTE_ID = "contributi_import_utente_id"


class CampagnaListaView(RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI
    template_name = "contributi/campagna_lista.html"
    context_object_name = "campagne"

    def get_queryset(self):
        return Campagna.objects.all()


class CampagnaCreaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_CAMPAGNA
    ruoli_ammessi_solo_diretti = True
    template_name = "contributi/campagna_crea.html"

    def get(self, request):
        return render(request, self.template_name, {"form": CampagnaForm()})

    def post(self, request):
        form = CampagnaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        try:
            campagna = apri_campagna(utente=request.user, **form.cleaned_data)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"form": form})

        messages.success(request, "Campagna creata.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna.pk]))


class CampagnaDettaglioView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI
    template_name = "contributi/campagna_dettaglio.html"

    def get(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        partecipazioni = (
            partecipazioni_visibili(request.user, campagna)
            .select_related("capo", "gruppo", "tipologia")
            .prefetch_related("contributi")
        )
        return render(
            request,
            self.template_name,
            {"campagna": campagna, "partecipazioni": partecipazioni},
        )


class PartecipazioneInserisciView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI
    template_name = "contributi/partecipazione_inserisci.html"

    def get(self, request, campagna_id):
        campagna = get_object_or_404(Campagna, pk=campagna_id)
        return render(
            request, self.template_name, {"campagna": campagna, "form": PartecipazioneManualeForm()}
        )

    def post(self, request, campagna_id):
        campagna = get_object_or_404(Campagna, pk=campagna_id)
        form = PartecipazioneManualeForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        dati = form.cleaned_data
        try:
            inserisci_partecipazione_manuale(
                utente=request.user,
                campagna=campagna,
                codice_socio=dati["codice_socio"],
                tipologia=dati["tipologia"],
                data_inizio=dati["data_inizio"],
                data_fine=dati["data_fine"],
                luogo=dati["luogo"],
                quota_versata=dati["quota_versata"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        messages.success(request, "Partecipazione inserita.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna.pk]))


class PartecipazioniImportAnteprimaView(RuoloRequiredMixin, View):
    """L'anteprima non scrive nulla: il file caricato si legge solo in
    memoria e i bytes originali si tengono in sessione (DB-backed, base64)
    per la conferma, mai su disco (D-17)."""

    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI
    template_name = "contributi/partecipazioni_import_anteprima.html"

    def get(self, request, campagna_id):
        campagna = get_object_or_404(Campagna, pk=campagna_id)
        return render(
            request,
            self.template_name,
            {"campagna": campagna, "form": ImportazionePartecipazioniForm()},
        )

    def post(self, request, campagna_id):
        campagna = get_object_or_404(Campagna, pk=campagna_id)
        form = ImportazionePartecipazioniForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        file = form.cleaned_data["file"]
        contenuto = file.read()
        righe = _leggi_righe(file.name, contenuto)
        piano = costruisci_piano_partecipazioni(righe, campagna=campagna, utente=request.user)

        request.session[_SESSION_FILE_B64] = base64.b64encode(contenuto).decode("ascii")
        request.session[_SESSION_NOME_FILE] = file.name
        request.session[_SESSION_CAMPAGNA_ID] = campagna.pk
        request.session[_SESSION_UTENTE_ID] = request.user.pk

        return render(request, self.template_name, {"campagna": campagna, "piano": piano})


class PartecipazioniImportConfermaView(RuoloRequiredMixin, View):
    """POST-only: rilegge il file dalla sessione e ricalcola il piano da zero
    (mai riusa quello dell'anteprima), poi applica."""

    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI

    def post(self, request, campagna_id):
        campagna = get_object_or_404(Campagna, pk=campagna_id)

        file_b64 = request.session.get(_SESSION_FILE_B64)
        utente_id = request.session.get(_SESSION_UTENTE_ID)
        campagna_sessione_id = request.session.get(_SESSION_CAMPAGNA_ID)
        if not file_b64 or utente_id != request.user.pk or campagna_sessione_id != campagna.pk:
            messages.error(
                request, "L'anteprima è scaduta o non è più valida: ripeti il caricamento del file."
            )
            return redirect(
                reverse("contributi:partecipazioni_import_anteprima", args=[campagna.pk])
            )

        nome_file = request.session.get(_SESSION_NOME_FILE) or "partecipazioni"
        contenuto = base64.b64decode(file_b64)
        righe = _leggi_righe(nome_file, contenuto)
        piano = costruisci_piano_partecipazioni(righe, campagna=campagna, utente=request.user)

        if not piano.valido:
            messages.error(request, "Il caricamento non è più valido: ripeti l'operazione.")
            return redirect(
                reverse("contributi:partecipazioni_import_anteprima", args=[campagna.pk])
            )

        file_originale = ContentFile(contenuto, name=nome_file)
        importazione = applica_piano_partecipazioni(
            piano, file_originale=file_originale, utente=request.user
        )

        for chiave in (
            _SESSION_FILE_B64,
            _SESSION_NOME_FILE,
            _SESSION_CAMPAGNA_ID,
            _SESSION_UTENTE_ID,
        ):
            request.session.pop(chiave, None)

        messages.success(request, "Importazione partecipazioni completata.")
        return redirect(
            reverse("contributi:importazione_partecipazioni_dettaglio", args=[importazione.pk])
        )


class ImportazionePartecipazioniDettaglioView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI
    template_name = "contributi/importazione_partecipazioni_dettaglio.html"

    def get(self, request, pk):
        importazione = get_object_or_404(
            ImportazionePartecipazioni.objects.select_related("campagna", "utente"), pk=pk
        )
        return render(request, self.template_name, {"importazione": importazione})


class ModelloXlsxPartecipazioniView(RuoloRequiredMixin, View):
    """Genera al volo (mai su disco) il modello xlsx vuoto con le colonne del
    tracciato di D-21."""

    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI

    def get(self, request, campagna_id):
        get_object_or_404(Campagna, pk=campagna_id)
        cartella = Workbook()
        foglio = cartella.active
        foglio.append(list(COLONNE_TRACCIATO))
        buffer = io.BytesIO()
        cartella.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="modello_partecipazioni.xlsx"'
        return response


class CampagnaAvviaValutazioneView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_CAMPAGNA

    def post(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        try:
            avvia_valutazione(utente=request.user, campagna=campagna)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _messaggio(exc))
        else:
            messages.success(
                request,
                "Valutazione avviata: le tipologie ad approvazione automatica "
                "sono state approvate.",
            )
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna.pk]))


class CampagnaSimulaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_CAMPAGNA

    def post(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        try:
            risultato = simula_calcolo(utente=request.user, campagna=campagna)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _messaggio(exc))
        else:
            messages.success(
                request,
                f"Simulazione eseguita: {risultato.n} partecipazioni approvate, "
                f"quota proporzionale {risultato.quota_proporzionale:.2f}, "
                f"residuo {risultato.residuo:.2f}.",
            )
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna.pk]))


class CampagnaChiudiView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_CAMPAGNA

    def post(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        try:
            chiudi_campagna(request, utente=request.user, campagna=campagna)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _messaggio(exc))
        else:
            messages.success(request, "Campagna chiusa: importi congelati.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna.pk]))


class BonificiGeneraView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_CAMPAGNA
    template_name = "contributi/bonifici_genera.html"

    def get(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        causale_default = ImpostazioniPiattaforma.corrente().causale_bonifico_default or (
            f"Contributo FoCa {campagna.anno} - AGESCI Zona Hirpinia"
        )
        form = BonificiGeneraForm(initial={"causale": causale_default})
        return render(request, self.template_name, {"campagna": campagna, "form": form})

    def post(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        form = BonificiGeneraForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        try:
            righe = genera_righe_bonifici(campagna, causale=form.cleaned_data["causale"])
        except ValidationError as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        if form.cleaned_data["formato"] == "xlsx":
            return _bonifici_xlsx(righe, campagna)
        return _bonifici_csv(righe, campagna)


class CampagnaLiquidaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_CAMPAGNA
    template_name = "contributi/campagna_liquida.html"

    def get(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        return render(
            request, self.template_name, {"campagna": campagna, "form": LiquidaCampagnaForm()}
        )

    def post(self, request, pk):
        campagna = get_object_or_404(Campagna, pk=pk)
        form = LiquidaCampagnaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        try:
            liquida_campagna(
                request,
                utente=request.user,
                campagna=campagna,
                data_liquidazione=form.cleaned_data["data_liquidazione"],
                riferimento_bonifico=form.cleaned_data["riferimento_bonifico"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"campagna": campagna, "form": form})

        messages.success(request, "Campagna liquidata.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna.pk]))


class PartecipazioneApprovaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_VALUTAZIONE_PARTECIPAZIONI

    def post(self, request, campagna_id, pk):
        partecipazione = get_object_or_404(Partecipazione, pk=pk, campagna_id=campagna_id)
        try:
            approva_partecipazione(utente=request.user, partecipazione=partecipazione)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _messaggio(exc))
        else:
            messages.success(request, "Partecipazione approvata.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna_id]))


class PartecipazioneRespingiView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_VALUTAZIONE_PARTECIPAZIONI
    template_name = "contributi/partecipazione_respingi.html"

    def get(self, request, campagna_id, pk):
        partecipazione = get_object_or_404(Partecipazione, pk=pk, campagna_id=campagna_id)
        return render(
            request,
            self.template_name,
            {"partecipazione": partecipazione, "form": RespingiPartecipazioneForm()},
        )

    def post(self, request, campagna_id, pk):
        partecipazione = get_object_or_404(Partecipazione, pk=pk, campagna_id=campagna_id)
        form = RespingiPartecipazioneForm(request.POST)
        if not form.is_valid():
            return render(
                request, self.template_name, {"partecipazione": partecipazione, "form": form}
            )
        try:
            respingi_partecipazione(
                utente=request.user,
                partecipazione=partecipazione,
                motivazione=form.cleaned_data["motivazione"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(
                request, self.template_name, {"partecipazione": partecipazione, "form": form}
            )
        messages.success(request, "Partecipazione respinta.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna_id]))


class PartecipazioneRichiediDocumentiView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_VALUTAZIONE_PARTECIPAZIONI

    def post(self, request, campagna_id, pk):
        partecipazione = get_object_or_404(Partecipazione, pk=pk, campagna_id=campagna_id)
        try:
            richiedi_documenti(utente=request.user, partecipazione=partecipazione)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _messaggio(exc))
        else:
            messages.success(request, "Documentazione richiesta al gruppo.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna_id]))


class AllegatoPartecipazioneCaricaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI
    template_name = "contributi/allegato_carica.html"

    def get(self, request, campagna_id, pk):
        partecipazione = get_object_or_404(Partecipazione, pk=pk, campagna_id=campagna_id)
        return render(
            request,
            self.template_name,
            {"partecipazione": partecipazione, "form": AllegatoPartecipazioneForm()},
        )

    def post(self, request, campagna_id, pk):
        partecipazione = get_object_or_404(Partecipazione, pk=pk, campagna_id=campagna_id)
        form = AllegatoPartecipazioneForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request, self.template_name, {"partecipazione": partecipazione, "form": form}
            )
        try:
            carica_allegato(
                utente=request.user,
                partecipazione=partecipazione,
                file=form.cleaned_data["file"],
                tipo=form.cleaned_data["tipo"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(
                request, self.template_name, {"partecipazione": partecipazione, "form": form}
            )
        messages.success(request, "Documento caricato.")
        return redirect(reverse("contributi:campagna_dettaglio", args=[campagna_id]))


_COLONNE_BONIFICI = ["codice", "denominazione", "intestazione_conto", "iban", "importo", "causale"]


def _righe_bonifici_valori(righe: list[RigaBonifico]):
    for r in righe:
        yield [r.gruppo_codice, r.denominazione, r.intestazione_conto, r.iban, r.importo, r.causale]


def _bonifici_csv(righe: list[RigaBonifico], campagna: Campagna) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="bonifici_{campagna.anno}.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(_COLONNE_BONIFICI)
    for valori in _righe_bonifici_valori(righe):
        writer.writerow(valori)
    return response


def _bonifici_xlsx(righe: list[RigaBonifico], campagna: Campagna) -> HttpResponse:
    cartella = Workbook()
    foglio = cartella.active
    foglio.append(_COLONNE_BONIFICI)
    for valori in _righe_bonifici_valori(righe):
        foglio.append(valori)
    buffer = io.BytesIO()
    cartella.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="bonifici_{campagna.anno}.xlsx"'
    return response


def _leggi_righe(nome_file: str, contenuto: bytes):
    if nome_file.lower().endswith(".csv"):
        return leggi_righe_csv(contenuto.decode("utf-8-sig"))
    return leggi_righe_xlsx(contenuto)


def _messaggio(exc: Exception) -> str:
    if hasattr(exc, "messages"):
        return "; ".join(exc.messages)
    return str(exc)
