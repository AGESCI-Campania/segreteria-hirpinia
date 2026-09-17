"""Viste di F6b (sola lettura: elenco, dettaglio, download giustificativi) e
F6c (creazione nota/evento/riga documentale). Le transizioni FSM restano
F6d. Il perimetro è sempre quello di `note_visibili()`/`allegato_visibile()`
(D-66) o delle funzioni di `creazione.py`, mai un controllo di ruolo diretto
qui: un capo qualsiasi deve poter accedere alle proprie note."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.anagrafica.models import Capo, IncaricoUnita
from apps.core.messaggi import messaggi_per_campo, messaggio_utente

from .allegati import carica_allegato
from .anno_associativo import anno_associativo_per_data
from .creazione import aggiungi_riga_documentale, crea_nota_bozza, verifica_nota_modificabile
from .forms import EventoForm, NotaCreaForm, RigaSpesaDocumentaleForm
from .iban import maschera_iban
from .models import Allegato, StatoNota
from .permessi import e_beneficiario_della_nota, e_compilatore_della_nota, puo_gestire_note
from .visibilita import allegato_visibile, note_visibili


class NotaListaView(LoginRequiredMixin, ListView):
    template_name = "note_spese/nota_lista.html"
    context_object_name = "note"

    def get_queryset(self):
        return note_visibili(self.request.user).select_related(
            "beneficiario", "evento", "gruppo_censimento", "centro_costo"
        )


class NotaDettaglioView(LoginRequiredMixin, View):
    template_name = "note_spese/nota_dettaglio.html"

    def get(self, request, pk):
        nota = get_object_or_404(
            note_visibili(request.user).select_related(
                "beneficiario",
                "compilatore",
                "evento",
                "gruppo_censimento",
                "centro_costo",
                "incarico",
                "rilievo_riga",
            ),
            pk=pk,
        )
        righe = nota.righe.select_related(
            "categoria", "localita_partenza", "localita_arrivo"
        ).prefetch_related("allegati", "passeggeri")
        puo_modificare = nota.stato == StatoNota.BOZZA and (
            e_beneficiario_della_nota(request.user, nota)
            or e_compilatore_della_nota(request.user, nota)
        )
        contesto = {
            "nota": nota,
            "righe": righe,
            "iban_mascherato": maschera_iban(nota.iban),
            "autorizzazioni_rdz": nota.autorizzazioni_rdz.select_related("utente"),
            "puo_gestire_note": puo_gestire_note(request.user),
            "puo_modificare": puo_modificare,
        }
        return render(request, self.template_name, contesto)


class AllegatoScaricaView(LoginRequiredMixin, View):
    def get(self, request, pk):
        allegato = get_object_or_404(Allegato, pk=pk)
        if not allegato_visibile(request.user, allegato):
            raise PermissionDenied(
                "Non hai visibilità su nessuna delle note collegate a questo allegato."
            )
        nome_file = allegato.file.name.rsplit("/", 1)[-1]
        return FileResponse(allegato.file.open("rb"), filename=nome_file)


def _applica_errori(form, exc: PermissionDenied | ValidationError) -> None:
    campi = messaggi_per_campo(exc) if isinstance(exc, ValidationError) else None
    if campi:
        for campo, testo in campi.items():
            if campo in form.fields:
                form.add_error(campo, testo)
            else:
                form.add_error(None, testo)
    else:
        form.add_error(None, messaggio_utente(exc))


class NotaCreaView(LoginRequiredMixin, View):
    """F6c: creazione della testata in `BOZZA`. Nessuna riga qui — si
    aggiungono dal dettaglio, una volta creata la nota (D-44: le righe
    seguono la testata, non il contrario)."""

    template_name = "note_spese/nota_crea.html"

    def _incarichi_disponibili(self, request):
        if request.user.codice_socio is None:
            return IncaricoUnita.objects.none()
        anno = anno_associativo_per_data(timezone.now().date())
        return IncaricoUnita.objects.filter(
            capo_id=request.user.codice_socio, anno_scout=anno, cessato_il__isnull=True
        )

    def get(self, request):
        form = NotaCreaForm(incarichi_disponibili=self._incarichi_disponibili(request))
        return render(
            request,
            self.template_name,
            {"form": form, "puo_gestire_note": puo_gestire_note(request.user)},
        )

    def post(self, request):
        form = NotaCreaForm(
            request.POST, incarichi_disponibili=self._incarichi_disponibili(request)
        )
        contesto = {"form": form, "puo_gestire_note": puo_gestire_note(request.user)}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        dati = form.cleaned_data
        codice_terzi = dati["beneficiario_codice_socio"].strip()
        try:
            if codice_terzi:
                if not puo_gestire_note(request.user):
                    raise PermissionDenied(
                        "Solo chi gestisce le note può crearne una per un altro capo (D-36)."
                    )
                beneficiario = Capo.objects.filter(pk=codice_terzi).first()
                if beneficiario is None:
                    raise ValidationError(
                        {
                            "beneficiario_codice_socio": f"Nessun capo con codice socio {codice_terzi}."
                        }
                    )
            elif request.user.codice_socio is not None:
                beneficiario = Capo.objects.get(pk=request.user.codice_socio)
            else:
                raise ValidationError(
                    "Il tuo account non è associato a un capo: indica un codice socio beneficiario."
                )

            nota = crea_nota_bozza(
                utente=request.user,
                beneficiario=beneficiario,
                evento=dati["evento"],
                incarico=dati["incarico"],
                incarico_altro=dati["incarico_altro"],
                iban=dati["iban"],
                intestatario_iban=dati["intestatario_iban"],
            )
        except (PermissionDenied, ValidationError) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, "Nota spese creata in bozza.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class EventoCreaView(LoginRequiredMixin, View):
    """D-49: un evento creato da un capo entra subito nell'elenco comune,
    marcato non validato (default già in `Evento.validato`)."""

    template_name = "note_spese/evento_crea.html"

    def get(self, request):
        form = EventoForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = EventoForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        evento = form.save(commit=False)
        evento.creato_da = request.user
        try:
            evento.full_clean()
        except ValidationError as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, {"form": form})
        evento.save()
        messages.success(request, "Evento creato, in attesa di validazione.")
        return redirect(reverse("note_spese:nota_crea"))


class RigaCreaView(LoginRequiredMixin, View):
    """F6c: solo categorie documentali (D-45) — le categorie chilometriche
    hanno un'interfaccia dedicata, non ancora scritta."""

    template_name = "note_spese/riga_crea.html"

    def get(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        try:
            verifica_nota_modificabile(nota, request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))
        form = RigaSpesaDocumentaleForm()
        return render(request, self.template_name, {"form": form, "nota": nota})

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = RigaSpesaDocumentaleForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "nota": nota})

        try:
            aggiungi_riga_documentale(
                nota=nota,
                utente=request.user,
                categoria=form.cleaned_data["categoria"],
                data=form.cleaned_data["data_spesa"],
                importo=form.cleaned_data["importo"],
                descrizione=form.cleaned_data["descrizione"],
                tratta_testo=form.cleaned_data["tratta_testo"],
            )
        except ValidationError as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, {"form": form, "nota": nota})

        messages.success(request, "Riga aggiunta.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class AllegatoCaricaView(LoginRequiredMixin, View):
    """F6c: carica un giustificativo su una riga già esistente della nota.
    Un solo file per volta, collegato a una sola riga — il caso "documento
    cumulativo su più righe" (D-58) resta un'estensione futura di questa
    stessa vista, non necessaria per il primo giro di compilazione."""

    template_name = "note_spese/allegato_carica.html"

    def _riga(self, request, nota_pk, riga_pk):
        nota = get_object_or_404(note_visibili(request.user), pk=nota_pk)
        riga = get_object_or_404(nota.righe, pk=riga_pk)
        return nota, riga

    def get(self, request, nota_pk, riga_pk):
        nota, riga = self._riga(request, nota_pk, riga_pk)
        try:
            verifica_nota_modificabile(nota, request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))
        return render(request, self.template_name, {"nota": nota, "riga": riga})

    def post(self, request, nota_pk, riga_pk):
        nota, riga = self._riga(request, nota_pk, riga_pk)
        file = request.FILES.get("file")
        contesto = {"nota": nota, "riga": riga}
        if file is None:
            messages.error(request, "Seleziona un file da caricare.")
            return render(request, self.template_name, contesto)
        try:
            verifica_nota_modificabile(nota, request.user)
            carica_allegato(file, [riga], request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return render(request, self.template_name, contesto)

        messages.success(request, "Allegato caricato.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))
