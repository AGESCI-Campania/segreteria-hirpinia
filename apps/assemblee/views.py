from __future__ import annotations

import base64

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.accounts.models import Utente
from apps.core.mixins import BreadcrumbExtraMixin
from apps.organizzazione.models import Gruppo

from . import cruscotto, elenco, email_aventi, odg, sedute
from . import deleghe as deleghe_ae
from . import file as file_assemblea
from . import quorum as quorum_assemblea
from . import verbale as verbale_assemblea
from . import votazioni as voto
from .forms import (
    AssembleaCreaForm,
    AventeInserisciForm,
    ConvocazioneForm,
    DelegaForm,
    EmailAventeForm,
    ImportEmailForm,
    IncaricoDichiaratoFormSet,
    OperatoreAggiungiForm,
    PuntoOdGForm,
    QualificheForm,
    TrasferisciForm,
    VariazioneRappresentanteForm,
    VerbaleForm,
    VotazioneForm,
    form_risultati,
)
from .models import (
    Assemblea,
    AventeDiritto,
    DelegaAE,
    ImportazioneEmail,
    OperatoreVoto,
    PuntoOdG,
    RichiedenteVerifica,
    Seduta,
    TipoAppello,
    Votazione,
)
from .permessi import accede_assemblee, assemblee_visibili, puo_gestire_assemblee, puo_operare
from .quorum import stato_quorum


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
            "ae_gruppo_ids": deleghe_ae.ae_gruppo_ids(righe),
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


# --- Sedute e presenze -----------------------------------------------------------


def _seduta_visibile(request: HttpRequest, pk: int, seduta_pk: int) -> Seduta:
    assemblea = _assemblea_visibile(request, pk)
    return get_object_or_404(Seduta, pk=seduta_pk, assemblea=assemblea)


def _breadcrumb_seduta(request, *ultimi: dict) -> list[dict]:
    seduta = Seduta.objects.filter(pk=request.resolver_match.kwargs.get("seduta_pk")).first()
    return _breadcrumb_assemblea(request, {"label": str(seduta) if seduta else ""}, *ultimi)


class SedutaView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/seduta.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request)

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        assemblea = seduta.assemblea
        verifica = quorum_assemblea.verifica_in_corso(seduta)
        contesto = {
            "assemblea": assemblea,
            "seduta": seduta,
            "quorum": stato_quorum(seduta),
            "verifica": verifica,
            "verifica_senza_quorum": quorum_assemblea.verifica_senza_quorum(seduta),
            "puo_gestire": puo_gestire_assemblee(request.user),
            "stato_verifica": stato_quorum(seduta, verifica) if verifica else None,
            "verifiche_chiuse": seduta.appelli.filter(
                tipo=TipoAppello.VERIFICA, chiuso_il__isnull=False
            ).order_by("numero"),
            "richiedenti": RichiedenteVerifica.choices,
            "puo_operare": puo_operare(request.user, assemblea) and not assemblea.conclusa,
            "puo_nuova_convocazione": (
                puo_gestire_assemblee(request.user)
                and seduta.costituita is False
                and seduta == sedute.seduta_corrente(assemblea)
                and seduta.convocazione < Seduta.Convocazione.TERZA
            ),
        }
        return render(request, self.template_name, contesto)


AZIONI_SEDUTA = {
    "apri": (sedute.apri_seduta, "Seduta aperta: si possono registrare le presenze."),
    "costituita": (sedute.dichiara_costituita, "Seduta dichiarata validamente costituita."),
    "non_costituita": (
        sedute.dichiara_non_costituita,
        "Seduta chiusa: quorum costitutivo non raggiunto.",
    ),
    "chiudi": (sedute.chiudi_lavori, "Lavori chiusi."),
    "chiudi_verifica": (
        sedute.chiudi_verifica,
        "Verifica chiusa: da ora contano i presenti rilevati.",
    ),
    "annulla_verifica": (sedute.annulla_verifica, "Verifica del quorum annullata."),
}


# Azioni che chiudono la seduta e non si possono annullare: richiedono la
# conferma esplicita anche lato server, non solo la casella `required` nel form.
AZIONI_DA_CONFERMARE = {"non_costituita", "chiudi", "chiudi_verifica", "annulla_verifica"}


class SedutaAzioneView(LoginRequiredMixin, View):
    """I permessi li controlla il service layer (gestori e operatori)."""

    def post(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        nome_azione = request.POST.get("azione", "")
        azione = AZIONI_SEDUTA.get(nome_azione)
        if nome_azione == "apri_verifica":
            try:
                sedute.apri_verifica(seduta, request.POST.get("richiedente", ""), request.user)
            except ValidationError as errore:
                messages.error(request, " ".join(errore.messages))
            else:
                messages.success(
                    request, "Verifica del quorum aperta: rifate l'appello dalla pagina presenze."
                )
        elif azione is None:
            messages.error(request, "Azione non riconosciuta.")
        elif nome_azione in AZIONI_DA_CONFERMARE and request.POST.get("conferma") != "1":
            messages.error(request, "Spunta la conferma prima di chiudere la seduta.")
        else:
            funzione, messaggio = azione
            try:
                funzione(seduta, request.user)
            except ValidationError as errore:
                messages.error(request, " ".join(errore.messages))
            else:
                messages.success(request, messaggio)
        return redirect(reverse("assemblee:seduta", args=[pk, seduta_pk]))


class NuovaConvocazioneView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/convocazione_nuova.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Nuova convocazione"})

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        return render(
            request, self.template_name, {"assemblea": assemblea, "form": ConvocazioneForm()}
        )

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        form = ConvocazioneForm(request.POST)
        if form.is_valid():
            try:
                seduta = sedute.crea_convocazione_successiva(
                    assemblea,
                    request.user,
                    data=form.cleaned_data["data_convocazione"],
                    ora=form.cleaned_data["ora_convocazione"],
                    luogo=form.cleaned_data["luogo"],
                )
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, f"{seduta} creata.")
                return redirect(reverse("assemblee:seduta", args=[pk, seduta.pk]))
        return render(request, self.template_name, {"assemblea": assemblea, "form": form})


class PresenzeView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """Registrazione delle presenze all'ingresso, pensata per lo smartphone."""

    template_name = "assemblee/presenze.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Presenze"})

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        assemblea = seduta.assemblea
        appello = quorum_assemblea.appello_attivo(seduta)
        presenti_ids = (
            set(appello.presenze.values_list("avente_id", flat=True)) if appello else set()
        )
        righe = assemblea.aventi_diritto.nell_elenco().select_related("gruppo")
        filtro_gruppo = request.GET.get("gruppo", "")
        cerca = request.GET.get("q", "").strip()
        solo_assenti = request.GET.get("assenti") == "1"
        verifica = quorum_assemblea.verifica_in_corso(seduta)
        # Durante una verifica: chi era presente all'appello precedente e non è
        # ancora stato rispuntato, per rifare l'appello partendo da loro.
        precedenti_ids: set[int] = set()
        if verifica is not None:
            precedenti_ids = set(quorum_assemblea.presenti(seduta).values_list("pk", flat=True))
        solo_precedenti = verifica is not None and request.GET.get("precedenti") == "1"
        if solo_precedenti:
            righe = righe.filter(pk__in=precedenti_ids).exclude(pk__in=presenti_ids)
        if filtro_gruppo:
            righe = righe.filter(gruppo_id=filtro_gruppo)
        if cerca:
            righe = righe.filter(
                Q(cognome__icontains=cerca) | Q(nome__icontains=cerca) | Q(codice_socio=cerca)
            )
        if solo_assenti:
            righe = righe.exclude(pk__in=presenti_ids)
        contesto = {
            "assemblea": assemblea,
            "seduta": seduta,
            "appello": appello,
            "righe": righe.order_by("cognome", "nome"),
            "presenti_ids": presenti_ids,
            "quorum": stato_quorum(seduta),
            "verifica": verifica,
            "stato_verifica": stato_quorum(seduta, verifica) if verifica else None,
            "precedenti_ids": precedenti_ids,
            "solo_precedenti": solo_precedenti,
            "gruppi": Gruppo.objects.filter(
                pk__in=assemblea.aventi_diritto.nell_elenco().values_list("gruppo_id", flat=True)
            ).order_by("nome"),
            "filtro_gruppo": filtro_gruppo,
            "cerca": cerca,
            "solo_assenti": solo_assenti,
            "puo_operare": puo_operare(request.user, assemblea) and seduta.aperta,
        }
        return render(request, self.template_name, contesto)


class PresenzaView(LoginRequiredMixin, View):
    def post(self, request, pk, seduta_pk, avente_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        try:
            if request.POST.get("annulla") == "1":
                sedute.annulla_presenza(seduta, avente, request.user)
            else:
                sedute.registra_presenza(seduta, avente, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return _torna_all_elenco(request, seduta.assemblea)


# --- Deleghe AE e qualifiche -----------------------------------------------------


class DelegheView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """Deleghe degli AE per una seduta (art. 5), registrate al banco."""

    template_name = "assemblee/deleghe.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Deleghe AE"})

    def _contesto(self, request, seduta, form=None):
        assemblea = seduta.assemblea
        elenco_qs = assemblea.aventi_diritto.nell_elenco().select_related("gruppo")
        gia_deleganti = seduta.deleghe.values_list("delegante_id", flat=True)
        deleganti = deleghe_ae.possono_delegare(elenco_qs.exclude(pk__in=gia_deleganti))
        if form is None:
            form = DelegaForm(deleganti=deleganti, aventi=elenco_qs.order_by("cognome", "nome"))
        return {
            "assemblea": assemblea,
            "seduta": seduta,
            "deleghe": seduta.deleghe.select_related(
                "delegante__gruppo", "delegato__gruppo"
            ).order_by("delegante__cognome"),
            "form": form,
            "puo_operare": puo_operare(request.user, assemblea) and seduta.chiusa_il is None,
            "nessun_ae": not deleghe_ae.possono_delegare(elenco_qs),
        }

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        return render(request, self.template_name, self._contesto(request, seduta))

    def post(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        contesto = self._contesto(request, seduta)
        form = DelegaForm(
            request.POST,
            deleganti=list(contesto["form"].fields["delegante"].queryset),
            aventi=contesto["form"].fields["delegato"].queryset,
        )
        if form.is_valid():
            try:
                delega = deleghe_ae.registra_delega(
                    seduta,
                    form.cleaned_data["delegante"],
                    form.cleaned_data["delegato"],
                    request.user,
                )
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, f"Delega registrata: {delega}.")
                return redirect(reverse("assemblee:deleghe", args=[pk, seduta_pk]))
        return render(request, self.template_name, self._contesto(request, seduta, form))


class DelegaRevocaView(LoginRequiredMixin, View):
    def post(self, request, pk, seduta_pk, delega_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        delega = get_object_or_404(DelegaAE, pk=delega_pk, seduta=seduta)
        try:
            deleghe_ae.revoca_delega(delega, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, f"Delega revocata: {delega}.")
        return redirect(reverse("assemblee:deleghe", args=[pk, seduta_pk]))


class QualificheView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/avente_qualifiche.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Qualifiche"},
        )

    def get(self, request, pk, avente_pk):
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        form = QualificheForm(
            initial={"ae_zona": avente.ae_zona, "rdz": avente.rdz, "comitato": avente.comitato}
        )
        contesto = {
            "avente": avente,
            "assemblea": avente.assemblea,
            "form": form,
            "ae_gruppo": deleghe_ae.e_ae_gruppo(avente),
        }
        return render(request, self.template_name, contesto)

    def post(self, request, pk, avente_pk):
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        form = QualificheForm(request.POST)
        if form.is_valid():
            try:
                deleghe_ae.aggiorna_qualifiche(avente, request.user, **form.cleaned_data)
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, f"Qualifiche di {avente} aggiornate.")
                return redirect(
                    reverse("assemblee:elenco", args=[pk]) + f"?gruppo={avente.gruppo_id}"
                )
        contesto = {
            "avente": avente,
            "assemblea": avente.assemblea,
            "form": form,
            "ae_gruppo": deleghe_ae.e_ae_gruppo(avente),
        }
        return render(request, self.template_name, contesto)


# --- Email degli aventi diritto (Excel per gruppo) ------------------------------

_SESSION_EMAIL = "assemblee_import_email"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _breadcrumb_email(request, *ultimi: dict) -> list[dict]:
    pk = request.resolver_match.kwargs["pk"]
    return _breadcrumb_assemblea(
        request,
        {"label": "Email degli aventi", "url": reverse("assemblee:email_aventi", args=[pk])},
        *ultimi,
    )


class EmailAventiView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Un Excel per gruppo da far verificare ai capigruppo, e il suo reimport."""

    template_name = "assemblee/email_aventi.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Email degli aventi"})

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        return render(request, self.template_name, self._contesto(assemblea, ImportEmailForm()))

    @staticmethod
    def _contesto(assemblea: Assemblea, form) -> dict:
        elenco_attuale = assemblea.aventi_diritto.nell_elenco()
        gruppi = []
        for gruppo in email_aventi.gruppi_con_aventi(assemblea):
            del_gruppo = elenco_attuale.filter(gruppo=gruppo)
            gruppi.append(
                {
                    "gruppo": gruppo,
                    "aventi": del_gruppo.count(),
                    "senza_email": del_gruppo.filter(email="").count(),
                }
            )
        return {
            "assemblea": assemblea,
            "gruppi": gruppi,
            "form": form,
            "importazioni": assemblea.importazioni_email.select_related("utente")[:20],
        }


class EmailGruppoView(GestisceAssembleeMixin, View):
    def get(self, request, pk, codice):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        gruppo = get_object_or_404(Gruppo, pk=codice)
        contenuto = email_aventi.genera_excel_gruppo(assemblea, gruppo, request.user)
        risposta = HttpResponse(contenuto, content_type=XLSX)
        nome = email_aventi.nome_file_gruppo(assemblea, gruppo)
        risposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta


class EmailZipView(GestisceAssembleeMixin, View):
    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        contenuto = email_aventi.genera_zip_gruppi(assemblea, request.user)
        risposta = HttpResponse(contenuto, content_type="application/zip")
        nome = f"email-aventi-{assemblea.anno_scout}-{assemblea.pk}.zip"
        risposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta


class ImportEmailAnteprimaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """L'anteprima non scrive nulla: il file resta in sessione (DB-backed) per
    la conferma, mai su disco, come gli import dell'anagrafica."""

    template_name = "assemblee/email_import_anteprima.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_email(request, {"label": "Anteprima dell'import"})

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        form = ImportEmailForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request, EmailAventiView.template_name, EmailAventiView._contesto(assemblea, form)
            )
        file = form.cleaned_data["file"]
        contenuto = file.read()
        anteprima = email_aventi.anteprima_import(assemblea, email_aventi.leggi_excel(contenuto))
        request.session[_SESSION_EMAIL] = {
            "assemblea": assemblea.pk,
            "utente": request.user.pk,
            "nome_file": file.name,
            "contenuto": base64.b64encode(contenuto).decode("ascii"),
        }
        return render(request, self.template_name, {"assemblea": assemblea, "anteprima": anteprima})


class ImportEmailConfermaView(GestisceAssembleeMixin, View):
    """Rilegge il file dalla sessione e ricalcola tutto da capo in
    `applica_import()`: mai l'anteprima già mostrata."""

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        dati = request.session.get(_SESSION_EMAIL)
        if not dati or dati["assemblea"] != assemblea.pk or dati["utente"] != request.user.pk:
            messages.error(request, "L'anteprima è scaduta: ricarica il file.")
            return redirect(reverse("assemblee:email_aventi", args=[pk]))
        try:
            importazione = email_aventi.applica_import(
                assemblea, base64.b64decode(dati["contenuto"]), dati["nome_file"], request.user
            )
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            request.session.pop(_SESSION_EMAIL, None)
            messages.success(
                request,
                f"Import completato: {importazione.email_aggiornate} email aggiornate "
                f"su {importazione.righe_lette} righe.",
            )
        return redirect(reverse("assemblee:email_aventi", args=[pk]))


class ImportEmailReportView(GestisceAssembleeMixin, View):
    def get(self, request, pk, importazione_pk):
        importazione = get_object_or_404(ImportazioneEmail, pk=importazione_pk, assemblea_id=pk)
        risposta = HttpResponse(
            "\ufeff" + email_aventi.report_csv(importazione), content_type="text/csv"
        )
        risposta["Content-Disposition"] = (
            f'attachment; filename="anomalie-email-{importazione.pk}.csv"'
        )
        return risposta


class AventeEmailView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """Correzione dell'email di un avente: gestori e operatori al banco."""

    template_name = "assemblee/avente_email.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Email"},
        )

    def _avente(self, request, pk, avente_pk) -> AventeDiritto:
        assemblea = _assemblea_visibile(request, pk)
        if not puo_operare(request.user, assemblea):
            raise PermissionDenied
        return get_object_or_404(AventeDiritto, pk=avente_pk, assemblea=assemblea)

    def get(self, request, pk, avente_pk):
        avente = self._avente(request, pk, avente_pk)
        form = EmailAventeForm(initial={"email": avente.email})
        return render(request, self.template_name, {"avente": avente, "form": form})

    def post(self, request, pk, avente_pk):
        avente = self._avente(request, pk, avente_pk)
        form = EmailAventeForm(request.POST)
        if form.is_valid():
            try:
                elenco.aggiorna_email(avente, form.cleaned_data["email"], request.user)
            except ValidationError as errore:
                form.add_error("email", errore)
            else:
                messages.success(request, f"Email di {avente} aggiornata.")
                return redirect(
                    reverse("assemblee:elenco", args=[pk]) + f"?gruppo={avente.gruppo_id}"
                )
        return render(request, self.template_name, {"avente": avente, "form": form})


# --- Cruscotto in tempo reale, proiettore, abilitazione app ----------------------


class StatoSedutaView(AccedeAssembleeMixin, View):
    """JSON per l'aggiornamento automatico (polling): l'elenco nominativo solo
    con ?elenco=1, mai per la vista proiettore."""

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        dati = cruscotto.stato_seduta(seduta, con_elenco=request.GET.get("elenco") == "1")
        risposta = JsonResponse(dati)
        risposta["Cache-Control"] = "no-store"
        return risposta


class CruscottoView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/cruscotto.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Cruscotto"})

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        contesto = {
            "assemblea": seduta.assemblea,
            "seduta": seduta,
            "stato": cruscotto.stato_seduta(seduta, con_elenco=True),
            "intervallo_ms": cruscotto.INTERVALLO_AGGIORNAMENTO_MS,
        }
        return render(request, self.template_name, contesto)


class ProiettoreView(AccedeAssembleeMixin, View):
    """Schermo intero da proiettare in sala: solo numeri, nessun dato personale."""

    template_name = "assemblee/proiettore.html"

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        contesto = {
            "assemblea": seduta.assemblea,
            "seduta": seduta,
            "stato": cruscotto.stato_seduta(seduta),
            "intervallo_ms": cruscotto.INTERVALLO_AGGIORNAMENTO_MS,
        }
        return render(request, self.template_name, contesto)


class AbilitazioneAppView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """Presenti che votano in app, per chi li abilita sull'app nazionale:
    pulsante "Aggiorna", nessun aggiornamento automatico."""

    template_name = "assemblee/abilitazione_app.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Abilitazione app"})

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        contesto = {
            "assemblea": seduta.assemblea,
            "seduta": seduta,
            "presenti": cruscotto.presenti_in_app(seduta),
            "aggiornato_il": timezone.localtime(),
        }
        return render(request, self.template_name, contesto)


# --- Votazioni --------------------------------------------------------------------


def _votazione_visibile(request: HttpRequest, pk: int, seduta_pk: int, votazione_pk: int):
    seduta = _seduta_visibile(request, pk, seduta_pk)
    return get_object_or_404(Votazione, pk=votazione_pk, seduta=seduta)


class VotazioniView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/votazioni.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Votazioni"})

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        votazioni_seduta = seduta.votazioni.select_related("punto").prefetch_related(
            "risultati", "candidati"
        )
        contesto = {
            "assemblea": seduta.assemblea,
            "seduta": seduta,
            "votazioni": [(v, voto.frase_esito(v)) for v in votazioni_seduta],
            "puo_votare": puo_operare(request.user, seduta.assemblea)
            and seduta.aperta
            and seduta.costituita is True,
        }
        return render(request, self.template_name, contesto)


class NuovaVotazioneView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/votazione_nuova.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Nuova votazione"})

    def get(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        form = VotazioneForm(assemblea=seduta.assemblea)
        return render(
            request,
            self.template_name,
            {"seduta": seduta, "assemblea": seduta.assemblea, "form": form},
        )

    def post(self, request, pk, seduta_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        form = VotazioneForm(request.POST, assemblea=seduta.assemblea)
        if form.is_valid():
            dati = form.cleaned_data
            candidati = [*dati["candidati"], *dati["altri_candidati"].splitlines()]
            try:
                votazione = voto.apri_votazione(
                    seduta,
                    request.user,
                    tipo=dati["tipo"],
                    oggetto=dati["oggetto"],
                    punto=dati["punto"],
                    incarico=dati["incarico"],
                    posti=dati["posti"],
                    candidati=candidati,
                )
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, f"Votazione aperta: {votazione.oggetto}.")
                return redirect(reverse("assemblee:votazione", args=[pk, seduta_pk, votazione.pk]))
        return render(
            request,
            self.template_name,
            {"seduta": seduta, "assemblea": seduta.assemblea, "form": form},
        )


class VotazioneView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/votazione.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        kwargs = request.resolver_match.kwargs
        return _breadcrumb_seduta(
            request,
            {
                "label": "Votazioni",
                "url": reverse("assemblee:votazioni", args=[kwargs["pk"], kwargs["seduta_pk"]]),
            },
            {"label": "Votazione"},
        )

    def _contesto(self, request, votazione, form=None):
        canali_voto = voto.canali(votazione)
        if form is None and not votazione.chiusa:
            form = form_risultati(votazione, canali_voto)
        esito = voto.esito(votazione) if votazione.chiusa else None
        return {
            "assemblea": votazione.seduta.assemblea,
            "seduta": votazione.seduta,
            "votazione": votazione,
            "form": form,
            "soglia": voto.soglia(votazione),
            "esito": esito,
            "frase_esito": voto.frase_esito(votazione),
            "puo_operare": puo_operare(request.user, votazione.seduta.assemblea),
            "puo_ballottaggio": (
                esito is not None
                and esito.ballottaggio_proposto
                and not votazione.ballottaggi.exists()
                and votazione.seduta.aperta
            ),
            "ballottaggio": votazione.ballottaggi.first(),
        }

    def get(self, request, pk, seduta_pk, votazione_pk):
        votazione = _votazione_visibile(request, pk, seduta_pk, votazione_pk)
        return render(request, self.template_name, self._contesto(request, votazione))

    def post(self, request, pk, seduta_pk, votazione_pk):
        votazione = _votazione_visibile(request, pk, seduta_pk, votazione_pk)
        canali_voto = voto.canali(votazione)
        form = form_risultati(votazione, canali_voto, request.POST)
        if form.is_valid():
            dati = form.cleaned_data
            per_canale = {
                canale: {
                    voce: dati[f"{canale}_{voce}"]
                    for voce in ("favorevoli", "contrari", "astenuti", "bianche", "nulle")
                    if f"{canale}_{voce}" in dati
                }
                for canale in canali_voto
            }
            voti_candidati = {
                c.pk: {
                    chiave: dati[f"candidato_{c.pk}_{chiave}"]
                    for chiave in ("voti_app", "voti_carta")
                    if f"candidato_{c.pk}_{chiave}" in dati
                }
                for c in votazione.candidati.all()
            }
            try:
                voto.registra_risultati(
                    votazione,
                    request.user,
                    per_canale=per_canale,
                    voti_candidati=voti_candidati,
                )
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, voto.frase_esito(votazione))
                return redirect(reverse("assemblee:votazione", args=[pk, seduta_pk, votazione_pk]))
        return render(request, self.template_name, self._contesto(request, votazione, form))


class VotazioneAzioneView(LoginRequiredMixin, View):
    """Ballottaggio e annullamento: i permessi li controlla il service layer."""

    def post(self, request, pk, seduta_pk, votazione_pk):
        votazione = _votazione_visibile(request, pk, seduta_pk, votazione_pk)
        azione = request.POST.get("azione")
        try:
            if azione == "ballottaggio":
                ballottaggio = voto.apri_ballottaggio(votazione, request.user)
                messages.success(request, "Ballottaggio aperto: si vota solo su carta.")
                return redirect(
                    reverse("assemblee:votazione", args=[pk, seduta_pk, ballottaggio.pk])
                )
            if azione == "annulla" and request.POST.get("conferma") == "1":
                voto.annulla_votazione(votazione, request.user)
                messages.success(request, "Votazione annullata.")
                return redirect(reverse("assemblee:votazioni", args=[pk, seduta_pk]))
            messages.error(request, "Azione non riconosciuta o non confermata.")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return redirect(reverse("assemblee:votazione", args=[pk, seduta_pk, votazione_pk]))


# --- Ordine del giorno e verbale ---------------------------------------------------


class OdgView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/odg.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Ordine del giorno"})

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        titoli = set(assemblea.punti_odg.values_list("titolo", flat=True))
        contesto = {
            "assemblea": assemblea,
            "punti": assemblea.punti_odg.order_by("ordine"),
            "proposte": [t for t in odg.PUNTI_TIPICI if t not in titoli],
        }
        return render(request, self.template_name, contesto)

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        azione = request.POST.get("azione")
        try:
            if azione == "aggiungi":
                odg.aggiungi_punto(assemblea, request.user, request.POST.get("titolo", ""))
            elif azione in ("su", "giu", "elimina"):
                punto = get_object_or_404(
                    PuntoOdG, pk=request.POST.get("punto"), assemblea=assemblea
                )
                if azione == "elimina":
                    odg.elimina_punto(punto, request.user)
                else:
                    odg.sposta_punto(punto, request.user, su=azione == "su")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return redirect(reverse("assemblee:odg", args=[pk]))


class PuntoModificaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/punto_modifica.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Ordine del giorno",
                "url": reverse("assemblee:odg", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Punto"},
        )

    def get(self, request, pk, punto_pk):
        punto = get_object_or_404(PuntoOdG, pk=punto_pk, assemblea_id=pk)
        form = PuntoOdGForm(initial={"titolo": punto.titolo, "testo": punto.testo})
        return render(
            request,
            self.template_name,
            {"punto": punto, "assemblea": punto.assemblea, "form": form},
        )

    def post(self, request, pk, punto_pk):
        punto = get_object_or_404(PuntoOdG, pk=punto_pk, assemblea_id=pk)
        form = PuntoOdGForm(request.POST)
        if form.is_valid():
            try:
                odg.modifica_punto(punto, request.user, **form.cleaned_data)
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, "Punto salvato.")
                return redirect(reverse("assemblee:odg", args=[pk]))
        return render(
            request,
            self.template_name,
            {"punto": punto, "assemblea": punto.assemblea, "form": form},
        )


def _suggerimenti_verbale(seduta: Seduta) -> dict:
    """Nomi proposti nei campi del verbale (testo libero comunque ammesso)."""
    elenco_qs = seduta.assemblea.aventi_diritto.nell_elenco().order_by("cognome", "nome")
    codici_operatori = seduta.assemblea.operatori.exclude(utente__codice_socio=None).values_list(
        "utente__codice_socio", flat=True
    )

    def nomi(qs) -> list[str]:
        return [f"{a.cognome} {a.nome}" for a in qs]

    return {
        "nomi_aventi": nomi(elenco_qs),
        "nomi_scrutatori": nomi(elenco_qs.filter(codice_socio__in=list(codici_operatori))),
        "nomi_rdz": nomi(elenco_qs.filter(rdz=True)),
    }


class VerbaleView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/verbale.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_seduta(request, {"label": "Verbale"})

    def _contesto(self, seduta, form):
        return {
            "assemblea": seduta.assemblea,
            "seduta": seduta,
            "form": form,
            "punti": seduta.assemblea.punti_odg.count(),
            "votazioni_chiuse": seduta.votazioni.filter(chiusa_il__isnull=False).count(),
            "votazioni_aperte": seduta.votazioni.filter(chiusa_il__isnull=True).count(),
            **_suggerimenti_verbale(seduta),
        }

    def get(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        if seduta.costituita is not True:
            messages.error(request, "Il verbale si redige per una seduta validamente costituita.")
            return redirect(reverse("assemblee:seduta", args=[pk, seduta_pk]))
        form = VerbaleForm(instance=verbale_assemblea.verbale_della_seduta(seduta))
        return render(request, self.template_name, self._contesto(seduta, form))

    def post(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        if seduta.costituita is not True:
            raise PermissionDenied
        form = VerbaleForm(request.POST, instance=verbale_assemblea.verbale_della_seduta(seduta))
        if form.is_valid():
            form.save()
            messages.success(request, "Dati del verbale salvati.")
            return redirect(reverse("assemblee:verbale", args=[pk, seduta_pk]))
        return render(request, self.template_name, self._contesto(seduta, form))


class VerbalePdfView(GestisceAssembleeMixin, View):
    def get(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        try:
            contenuto = verbale_assemblea.genera_verbale_pdf(seduta, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
            return redirect(reverse("assemblee:seduta", args=[pk, seduta_pk]))
        risposta = HttpResponse(contenuto, content_type="application/pdf")
        nome = f"verbale-assemblea-{seduta.assemblea.anno_scout}-{seduta.data:%Y%m%d}.pdf"
        risposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta


class VariazioneRappresentanteView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    template_name = "assemblee/variazione_rappresentante.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        kwargs = request.resolver_match.kwargs
        return _breadcrumb_seduta(
            request,
            {
                "label": "Verbale",
                "url": reverse("assemblee:verbale", args=[kwargs["pk"], kwargs["seduta_pk"]]),
            },
            {"label": "Rappresentante legale"},
        )

    def _seduta(self, pk, seduta_pk) -> Seduta:
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        if seduta.costituita is not True:
            raise PermissionDenied
        return seduta

    def _contesto(self, seduta, form):
        return {
            "assemblea": seduta.assemblea,
            "seduta": seduta,
            "form": form,
            "variazione": verbale_assemblea.variazione_della_seduta(seduta),
            "rdz": seduta.assemblea.aventi_diritto.nell_elenco()
            .filter(rdz=True)
            .order_by("cognome", "nome"),
        }

    def get(self, request, pk, seduta_pk):
        seduta = self._seduta(pk, seduta_pk)
        form = VariazioneRappresentanteForm(
            instance=verbale_assemblea.variazione_della_seduta(seduta)
        )
        return render(request, self.template_name, self._contesto(seduta, form))

    def post(self, request, pk, seduta_pk):
        seduta = self._seduta(pk, seduta_pk)
        variazione = verbale_assemblea.variazione_della_seduta(seduta)
        url = reverse("assemblee:variazione_rappresentante", args=[pk, seduta_pk])
        if request.POST.get("azione") == "precompila":
            avente = get_object_or_404(
                AventeDiritto, pk=request.POST.get("avente"), assemblea_id=pk
            )
            try:
                verbale_assemblea.precompila_rappresentante(variazione, avente, request.user)
            except ValidationError as errore:
                messages.error(request, " ".join(errore.messages))
            else:
                messages.success(
                    request,
                    "Dati precompilati dall'anagrafica: controllali e completa la provincia di nascita.",
                )
            return redirect(url)
        form = VariazioneRappresentanteForm(request.POST, instance=variazione)
        if form.is_valid():
            form.save()
            messages.success(request, "Dati salvati.")
            return redirect(url)
        return render(request, self.template_name, self._contesto(seduta, form))


class VariazioneRappresentantePdfView(GestisceAssembleeMixin, View):
    def get(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        try:
            contenuto = verbale_assemblea.genera_variazione_pdf(seduta, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
            return redirect(reverse("assemblee:seduta", args=[pk, seduta_pk]))
        risposta = HttpResponse(contenuto, content_type="application/pdf")
        nome = f"verbale-rappresentante-legale-{seduta.data:%Y%m%d}.pdf"
        risposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta
