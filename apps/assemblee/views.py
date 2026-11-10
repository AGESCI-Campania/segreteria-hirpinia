from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView

from apps.accounts.models import Utente
from apps.core.mixins import BreadcrumbExtraMixin

from .forms import AssembleaCreaForm, OperatoreAggiungiForm
from .models import Assemblea, OperatoreVoto
from .permessi import accede_assemblee, assemblee_visibili, puo_gestire_assemblee


def _breadcrumb_assemblee() -> list[dict]:
    return [
        {"label": "Moduli"},
        {"label": "Assemblee", "url": reverse_lazy("assemblee:assemblea_lista")},
    ]


def _assemblea_visibile(request: HttpRequest, pk: int) -> Assemblea:
    assert isinstance(request.user, Utente)
    return get_object_or_404(assemblee_visibili(request.user), pk=pk)


class AccedeAssembleeMixin(LoginRequiredMixin, UserPassesTestMixin):
    request: HttpRequest

    def test_func(self) -> bool:
        assert isinstance(self.request.user, Utente)
        return accede_assemblee(self.request.user)


class GestisceAssembleeMixin(LoginRequiredMixin, UserPassesTestMixin):
    request: HttpRequest

    def test_func(self) -> bool:
        assert isinstance(self.request.user, Utente)
        return puo_gestire_assemblee(self.request.user)


class AssembleaListaView(AccedeAssembleeMixin, ListView):
    template_name = "assemblee/assemblea_lista.html"
    context_object_name = "assemblee"

    def get_queryset(self):
        return assemblee_visibili(self.request.user).prefetch_related("sedute")

    def get_context_data(self, **kwargs):
        contesto = super().get_context_data(**kwargs)
        contesto["puo_gestire"] = puo_gestire_assemblee(self.request.user)
        return contesto


class AssembleaCreaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/assemblea_crea.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return [*_breadcrumb_assemblee(), {"label": "Nuova assemblea"}]

    def get(self, request):
        return render(request, self.template_name, {"form": AssembleaCreaForm()})

    def post(self, request):
        form = AssembleaCreaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        form.instance.creata_da = request.user
        with transaction.atomic():
            assemblea = form.save()
        messages.success(request, f"{assemblea} creata.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[assemblea.pk]))


class AssembleaDettaglioView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """Riepilogo dell'assemblea: un cruscotto con le sue sedute, gli operatori
    di voto e un pulsante per ciascuna funzione del modulo."""

    template_name = "assemblee/assemblea_dettaglio.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        assemblea = Assemblea.objects.filter(pk=request.resolver_match.kwargs.get("pk")).first()
        return [*_breadcrumb_assemblee(), {"label": str(assemblea) if assemblea else ""}]

    def get(self, request, pk):
        assemblea = _assemblea_visibile(request, pk)
        puo_gestire = puo_gestire_assemblee(request.user)
        elenco = assemblea.aventi_diritto.nell_elenco()
        contesto = {
            "assemblea": assemblea,
            "sedute": assemblea.sedute.all(),
            "operatori": assemblea.operatori.select_related("utente"),
            "puo_gestire": puo_gestire,
            "totale_aventi_diritto": elenco.count(),
            "totale_app": elenco.filter(vota_in_app=True).count(),
            "form_operatore": OperatoreAggiungiForm(assemblea=assemblea) if puo_gestire else None,
        }
        return render(request, self.template_name, contesto)


class OperatoreAggiungiView(GestisceAssembleeMixin, View):
    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        if assemblea.conclusa:
            raise PermissionDenied("L'assemblea è conclusa.")
        form = OperatoreAggiungiForm(request.POST, assemblea=assemblea)
        if form.is_valid():
            OperatoreVoto.objects.create(
                assemblea=assemblea, utente=form.cleaned_data["utente"], nominato_da=request.user
            )
            messages.success(request, f"{form.cleaned_data['utente']} è ora operatore di voto.")
        else:
            messages.error(request, "Seleziona un utente valido.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[assemblea.pk]))


class OperatoreRimuoviView(GestisceAssembleeMixin, View):
    def post(self, request, pk, operatore_pk):
        operatore = get_object_or_404(OperatoreVoto, pk=operatore_pk, assemblea_id=pk)
        if operatore.assemblea.conclusa:
            raise PermissionDenied("L'assemblea è conclusa.")
        operatore.delete()
        messages.success(request, f"{operatore.utente} non è più operatore di voto.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))
