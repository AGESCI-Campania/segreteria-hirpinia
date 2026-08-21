"""Viste del ciclo di vita del gruppo (D-24): creazione, disattivazione,
riattivazione — stesso schema di `apps/contributi/views.py` (try/except
PermissionDenied/ValidationError → messaggio, mai una scrittura prima della
conferma esplicita)."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.accounts.mixins import RuoloRequiredMixin
from apps.contributi.disattivazione_gruppo import conta_effetti_disattivazione

from .allowlist import crea_voce_allowlist, elimina_voce_allowlist
from .forms import AllowlistCreaForm, GruppoCreaForm, GruppoDisattivaForm, GruppoRiattivaForm
from .gruppi import RUOLI_GESTIONE_GRUPPI, crea_gruppo, disattiva_gruppo, riattiva_gruppo
from .models import AllowlistGruppo, Gruppo, anno_scout_corrente


class GruppoListaView(RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/gruppo_lista.html"
    context_object_name = "gruppi"

    def get_queryset(self):
        return Gruppo.objects.all()

    def get_context_data(self, **kwargs):
        contesto = super().get_context_data(**kwargs)
        anno = anno_scout_corrente()
        # e_attivo(anno) richiede un argomento: non richiamabile dal
        # template, si precalcola qui un attributo semplice per riga.
        for gruppo in contesto["gruppi"]:
            gruppo.attivo_anno_corrente = gruppo.e_attivo(anno)
        contesto["anno_corrente"] = anno
        return contesto


class GruppoCreaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/gruppo_crea.html"

    def get(self, request):
        return render(request, self.template_name, {"form": GruppoCreaForm()})

    def post(self, request):
        form = GruppoCreaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        try:
            crea_gruppo(utente=request.user, **form.cleaned_data)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"form": form})
        messages.success(request, "Gruppo creato.")
        return redirect(reverse("organizzazione:gruppo_lista"))


class GruppoDisattivaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/gruppo_disattiva.html"

    def get(self, request, codice):
        gruppo = get_object_or_404(Gruppo, pk=codice)
        conteggi = conta_effetti_disattivazione(gruppo, anno_scout_corrente())
        return render(
            request,
            self.template_name,
            {"gruppo": gruppo, "conteggi": conteggi, "form": GruppoDisattivaForm()},
        )

    def post(self, request, codice):
        gruppo = get_object_or_404(Gruppo, pk=codice)
        form = GruppoDisattivaForm(request.POST)
        if not form.is_valid():
            conteggi = conta_effetti_disattivazione(gruppo, anno_scout_corrente())
            return render(
                request,
                self.template_name,
                {"gruppo": gruppo, "conteggi": conteggi, "form": form},
            )
        try:
            disattiva_gruppo(utente=request.user, gruppo=gruppo, motivo=form.cleaned_data["motivo"])
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            conteggi = conta_effetti_disattivazione(gruppo, anno_scout_corrente())
            return render(
                request,
                self.template_name,
                {"gruppo": gruppo, "conteggi": conteggi, "form": form},
            )
        messages.success(request, "Gruppo disattivato.")
        return redirect(reverse("organizzazione:gruppo_lista"))


class GruppoRiattivaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/gruppo_riattiva.html"

    def get(self, request, codice):
        gruppo = get_object_or_404(Gruppo, pk=codice)
        ultimo = gruppo.stati_annuali.order_by("-anno_scout").first()
        anno_proposto = (ultimo.anno_scout + 1) if ultimo else anno_scout_corrente()
        form = GruppoRiattivaForm(initial={"anno_scout": anno_proposto})
        return render(request, self.template_name, {"gruppo": gruppo, "form": form})

    def post(self, request, codice):
        gruppo = get_object_or_404(Gruppo, pk=codice)
        form = GruppoRiattivaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"gruppo": gruppo, "form": form})
        try:
            riattiva_gruppo(
                utente=request.user,
                gruppo=gruppo,
                anno_scout=form.cleaned_data["anno_scout"],
                motivo=form.cleaned_data["motivo"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"gruppo": gruppo, "form": form})
        messages.success(request, "Gruppo riattivato.")
        return redirect(reverse("organizzazione:gruppo_lista"))


class AllowlistListaView(RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/allowlist_lista.html"
    context_object_name = "voci"

    def get_queryset(self):
        return AllowlistGruppo.objects.all()


class AllowlistCreaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/allowlist_crea.html"

    def get(self, request):
        return render(request, self.template_name, {"form": AllowlistCreaForm()})

    def post(self, request):
        form = AllowlistCreaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        try:
            crea_voce_allowlist(utente=request.user, **form.cleaned_data)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, _messaggio(exc))
            return render(request, self.template_name, {"form": form})
        messages.success(request, "Voce allowlist creata.")
        return redirect(reverse("organizzazione:allowlist_lista"))


class AllowlistEliminaView(RuoloRequiredMixin, View):
    ruoli_ammessi = RUOLI_GESTIONE_GRUPPI
    template_name = "organizzazione/allowlist_elimina.html"

    def get(self, request, pk):
        voce = get_object_or_404(AllowlistGruppo, pk=pk)
        return render(request, self.template_name, {"voce": voce})

    def post(self, request, pk):
        voce = get_object_or_404(AllowlistGruppo, pk=pk)
        try:
            elimina_voce_allowlist(utente=request.user, voce=voce)
        except PermissionDenied as exc:
            messages.error(request, _messaggio(exc))
            return render(request, self.template_name, {"voce": voce})
        messages.success(request, "Voce allowlist eliminata.")
        return redirect(reverse("organizzazione:allowlist_lista"))


def _messaggio(exc: Exception) -> str:
    if hasattr(exc, "messages"):
        return "; ".join(exc.messages)
    return str(exc)
