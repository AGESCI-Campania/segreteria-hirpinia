from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.accounts.models import Utente
from apps.core.mixins import BreadcrumbExtraMixin
from apps.organizzazione.models import Gruppo

from . import elenco
from . import file as file_assemblea
from .forms import (
    AssembleaCreaForm,
    AventeInserisciForm,
    IncaricoDichiaratoFormSet,
    OperatoreAggiungiForm,
    TrasferisciForm,
)
from .models import Assemblea, AventeDiritto, OperatoreVoto
from .permessi import accede_assemblee, assemblee_visibili, puo_gestire_assemblee, puo_operare


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
            importati = elenco.importa_elenco(assemblea, request.user)
        messages.success(request, f"{assemblea} creata: {importati} aventi diritto importati.")
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


# --- Elenco degli aventi diritto -----------------------------------------------


def _torna_all_elenco(request: HttpRequest, assemblea: Assemblea):
    """Torna all'elenco conservando i filtri, se il `next` è interno al sito."""
    destinazione = request.POST.get("next", "")
    if destinazione and url_has_allowed_host_and_scheme(
        destinazione, allowed_hosts={request.get_host()}
    ):
        return redirect(destinazione)
    return redirect(reverse("assemblee:elenco", args=[assemblea.pk]))


def _breadcrumb_assemblea(request, *ultimi: dict) -> list[dict]:
    pk = request.resolver_match.kwargs.get("pk")
    assemblea = Assemblea.objects.filter(pk=pk).first()
    return [
        *_breadcrumb_assemblee(),
        {
            "label": str(assemblea) if assemblea else "",
            "url": reverse("assemblee:assemblea_dettaglio", args=[pk]),
        },
        *ultimi,
    ]


class ElencoView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/elenco.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Aventi diritto"})

    def get(self, request, pk):
        assemblea = _assemblea_visibile(request, pk)
        tutti = assemblea.aventi_diritto.select_related("gruppo", "gruppo_origine")
        nell_elenco = tutti.nell_elenco()
        filtro_gruppo = request.GET.get("gruppo", "")
        cerca = request.GET.get("q", "").strip()
        mostra_usciti = request.GET.get("usciti") == "1"

        righe = tutti if mostra_usciti else nell_elenco
        if filtro_gruppo:
            righe = righe.filter(gruppo_id=filtro_gruppo)
        if cerca:
            righe = righe.filter(
                Q(cognome__icontains=cerca) | Q(nome__icontains=cerca) | Q(codice_socio=cerca)
            )
        righe = righe.order_by("gruppo__nome", "cognome", "nome")

        puo_gestire = puo_gestire_assemblee(request.user)
        contesto = {
            "assemblea": assemblea,
            "righe": righe,
            "gruppi": Gruppo.objects.filter(
                pk__in=tutti.values_list("gruppo_id", flat=True)
            ).order_by("nome"),
            "filtro_gruppo": filtro_gruppo,
            "cerca": cerca,
            "mostra_usciti": mostra_usciti,
            "totale": nell_elenco.count(),
            "totale_app": nell_elenco.filter(vota_in_app=True).count(),
            "totale_carta": nell_elenco.filter(vota_in_app=False).count(),
            "totale_usciti": tutti.exclude(uscita="").count(),
            "da_togliere_dall_app": nell_elenco.filter(voto_cartaceo_il__isnull=False),
            "gruppi_da_aggiornare": (elenco.gruppi_da_aggiornare(assemblea) if puo_gestire else []),
            "puo_gestire": puo_gestire and not assemblea.conclusa,
            "puo_operare": puo_operare(request.user, assemblea) and not assemblea.conclusa,
        }
        return render(request, self.template_name, contesto)


class EliminaView(GestisceAssembleeMixin, View):
    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        aventi = assemblea.aventi_diritto.filter(pk__in=request.POST.getlist("aventi"))
        if not aventi:
            messages.error(request, "Seleziona almeno un capo da eliminare.")
            return _torna_all_elenco(request, assemblea)
        try:
            eliminati = elenco.elimina(aventi, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, f"{eliminati} capi eliminati dall'elenco.")
        return _torna_all_elenco(request, assemblea)


class RipristinaView(GestisceAssembleeMixin, View):
    def post(self, request, pk, avente_pk):
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        try:
            elenco.ripristina(avente, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, f"{avente} è di nuovo nell'elenco.")
        return _torna_all_elenco(request, avente.assemblea)


class PassaACartaView(LoginRequiredMixin, View):
    """Gestori e operatori (D-70): il controllo è nel service layer."""

    def post(self, request, pk, avente_pk):
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        annulla = request.POST.get("annulla") == "1"
        try:
            if annulla:
                elenco.annulla_passaggio_a_carta(avente, request.user)
            else:
                elenco.passa_a_carta(avente, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            if annulla:
                messages.success(request, f"{avente} torna a votare in app.")
            else:
                messages.warning(
                    request,
                    f"{avente} vota su carta: toglilo dall'app nazionale e verifica che non "
                    "vi abbia già votato.",
                )
        return _torna_all_elenco(request, avente.assemblea)


class TrasferisciView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/avente_trasferisci.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Trasferimento"},
        )

    def _contesto(self, avente, form):
        return {"avente": avente, "assemblea": avente.assemblea, "form": form}

    def get(self, request, pk, avente_pk):
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        form = TrasferisciForm(assemblea=avente.assemblea, attuale=avente.gruppo)
        return render(request, self.template_name, self._contesto(avente, form))

    def post(self, request, pk, avente_pk):
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        form = TrasferisciForm(request.POST, assemblea=avente.assemblea, attuale=avente.gruppo)
        if not form.is_valid():
            return render(request, self.template_name, self._contesto(avente, form))
        try:
            elenco.trasferisci(avente, form.cleaned_data["gruppo"], request.user)
        except ValidationError as errore:
            form.add_error(None, errore)
            return render(request, self.template_name, self._contesto(avente, form))
        messages.success(request, f"{avente} trasferito a {avente.gruppo}.")
        return redirect(reverse("assemblee:elenco", args=[pk]) + f"?gruppo={avente.gruppo_id}")


class InserisciView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/avente_inserisci.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Nuovo capo"},
        )

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        contesto = {
            "assemblea": assemblea,
            "form": AventeInserisciForm(
                assemblea=assemblea, initial={"gruppo": request.GET.get("gruppo")}
            ),
            "incarichi": IncaricoDichiaratoFormSet(prefix="incarichi"),
        }
        return render(request, self.template_name, contesto)

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        form = AventeInserisciForm(request.POST, assemblea=assemblea)
        incarichi = IncaricoDichiaratoFormSet(request.POST, prefix="incarichi")
        if form.is_valid() and incarichi.is_valid():
            try:
                avente = elenco.inserisci(
                    assemblea,
                    request.user,
                    incarichi=[f.cleaned_data for f in incarichi if f.cleaned_data],
                    **form.cleaned_data,
                )
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                modalita = "in app" if avente.vota_in_app else "su carta"
                messages.success(request, f"{avente} aggiunto all'elenco (vota {modalita}).")
                if request.POST.get("altro") == "1":
                    return redirect(
                        reverse("assemblee:inserisci", args=[pk]) + f"?gruppo={avente.gruppo_id}"
                    )
                return redirect(
                    reverse("assemblee:elenco", args=[pk]) + f"?gruppo={avente.gruppo_id}"
                )
        contesto = {"assemblea": assemblea, "form": form, "incarichi": incarichi}
        return render(request, self.template_name, contesto)


class AggiornaGruppoView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/aggiorna_gruppo.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Aggiorna gruppo"},
        )

    def get(self, request, pk, codice):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        gruppo = get_object_or_404(Gruppo, pk=codice)
        anteprima = elenco.anteprima_aggiorna_gruppo(assemblea, gruppo)
        return render(request, self.template_name, {"assemblea": assemblea, "anteprima": anteprima})

    def post(self, request, pk, codice):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        gruppo = get_object_or_404(Gruppo, pk=codice)
        try:
            elenco.applica_aggiorna_gruppo(
                assemblea,
                gruppo,
                request.user,
                omonimi_confermati=[int(x) for x in request.POST.getlist("omonimi")],
            )
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, f"{gruppo} aggiornato ai censiti {assemblea.anno_scout}.")
        return redirect(reverse("assemblee:elenco", args=[pk]) + f"?gruppo={gruppo.pk}")


# --- File -----------------------------------------------------------------------


class TracciatoView(GestisceAssembleeMixin, View):
    """Tracciato .xlsx per l'app di voto del Nazionale: rigenerabile in
    qualsiasi momento, ogni download è tracciato."""

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        contenuto = file_assemblea.genera_tracciato_xlsx(assemblea, request.user)
        risposta = HttpResponse(
            contenuto,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        nome = f"tracciato-app-voto-{assemblea.anno_scout}-{assemblea.pk}.xlsx"
        risposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta


class FoglioPresenzeView(GestisceAssembleeMixin, View):
    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        contenuto = file_assemblea.genera_foglio_presenze_pdf(assemblea, request.user)
        risposta = HttpResponse(contenuto, content_type="application/pdf")
        nome = f"foglio-presenze-{assemblea.anno_scout}-{assemblea.pk}.pdf"
        risposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta
