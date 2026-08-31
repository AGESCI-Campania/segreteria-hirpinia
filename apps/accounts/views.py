from axes.decorators import axes_dispatch
from django.contrib import messages
from django.contrib.auth import login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from apps.core.messaggi import messaggio_utente
from apps.core.mixins import BreadcrumbExtraMixin

from . import deleghe as deleghe_service
from . import inviti as inviti_service
from . import ruoli as ruoli_service
from .forms import AttivazioneForm, DelegaForm, InvitoSingoloForm, RecuperoOtpForm, RuoloAssegnaForm
from .mixins import RuoloRequiredMixin
from .models import Delega, InvitoAttivazione, Ruolo, Utente
from .permessi import puo_impersonare_qualcuno, ruoli_effettivi

# Visualizzazione dello storico inviti (M10): RDZ la mantiene pur avendo
# perso la creazione (RUOLI_INVITO_DIRETTO) — "può solo delegare".
RUOLI_CHE_INVITANO = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})
RUOLI_INVITO_DIRETTO = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA})


class AttesaView(TemplateView):
    template_name = "accounts/attesa.html"


class GruppoNonAttivoView(TemplateView):
    template_name = "accounts/gruppo_non_attivo.html"


@method_decorator(axes_dispatch, name="dispatch")
class AttivazioneView(FormView):
    """Attivazione tramite OTP (D-20): precompila email/codice se arrivano
    dal link dell'email, verifica il codice e imposta la password."""

    template_name = "accounts/attivazione.html"
    form_class = AttivazioneForm
    success_url = reverse_lazy("core:home")

    def get_initial(self):
        return {
            "email": self.request.GET.get("email", ""),
            "codice": self.request.GET.get("codice", ""),
        }

    def form_valid(self, form):
        try:
            utente = inviti_service.verifica_e_completa(
                email=form.cleaned_data["email"],
                codice=form.cleaned_data["codice"],
                password=form.cleaned_data["password1"],
            )
        except inviti_service.InvitoNonValidoError:
            form.add_error(
                None, "Codice non valido, scaduto o già utilizzato. Richiedine uno nuovo."
            )
            return self.form_invalid(form)

        login(self.request, utente, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Account attivato: benvenuto/a su Catello.")
        return super().form_valid(form)


@method_decorator(axes_dispatch, name="dispatch")
class RecuperoOtpView(FormView):
    """Recupero autonomo di un OTP scaduto (D-25): risposta sempre identica,
    che l'indirizzo sia censito o meno (anti-enumerazione)."""

    template_name = "accounts/recupero.html"
    form_class = RecuperoOtpForm
    success_url = reverse_lazy("accounts:recupero")

    def form_valid(self, form):
        inviti_service.richiedi_recupero(form.cleaned_data["email"])
        messages.info(
            self.request,
            "Se l'indirizzo è censito su Catello, riceverai a breve una nuova email "
            "con le istruzioni per l'attivazione.",
        )
        return super().form_valid(form)


class InvitoCreaView(BreadcrumbExtraMixin, RuoloRequiredMixin, FormView):
    """Invio di un singolo invito OTP per un ruolo amministrativo (D-20, M10).
    Perimetro ristretto ad ADMIN/SEGRETERIA: RDZ può solo delegare, non
    invitare direttamente. L'invito con `gruppo` (account funzionale/CG)
    resta nel solo flusso massivo da allowlist, non più qui."""

    ruoli_ammessi = RUOLI_INVITO_DIRETTO
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/invito_crea.html"
    form_class = InvitoSingoloForm
    success_url = reverse_lazy("accounts:invito_lista")

    @classmethod
    def breadcrumb_extra(cls, request):
        return [
            {"label": "Amministrazione"},
            {"label": "Ruoli", "url": reverse_lazy("accounts:ruolo_lista")},
            {"label": "Nuovo invito"},
        ]

    def form_valid(self, form):
        inviti_service.crea_invito(
            email=form.cleaned_data["email"],
            creato_da=self.request.user,
            ruolo_proposto=form.cleaned_data["ruolo_proposto"],
        )
        messages.success(self.request, f"Invito inviato a {form.cleaned_data['email']}.")
        return super().form_valid(form)


class InvitoListaView(BreadcrumbExtraMixin, RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_CHE_INVITANO
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/invito_lista.html"
    context_object_name = "inviti"
    paginate_by = 50

    @classmethod
    def breadcrumb_extra(cls, request):
        return [
            {"label": "Amministrazione"},
            {"label": "Ruoli", "url": reverse_lazy("accounts:ruolo_lista")},
            {"label": "Storico inviti"},
        ]

    def get_queryset(self):
        return InvitoAttivazione.objects.select_related("gruppo", "creato_da").all()


class DelegheListaView(RuoloRequiredMixin, ListView):
    """Le proprie deleghe concesse (qualunque ruolo effettivo può vederle)."""

    template_name = "accounts/deleghe_lista.html"
    context_object_name = "deleghe"

    def test_func(self) -> bool:
        return self.request.user.is_authenticated

    def get_queryset(self):
        return Delega.objects.filter(delegante=self.request.user).select_related(
            "ruolo", "delegato"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ruoli_delegabili"] = [
            r.ruolo for r in ruoli_effettivi(self.request.user, alla_data=None) if not r.is_delega
        ]
        return ctx


class DelegheZonaListaView(RuoloRequiredMixin, ListView):
    """SEGRETERIA e ADMIN vedono e revocano qualsiasi delega (D-26): perimetro
    esplicito su ruolo effettivo, non su gruppi_visibili()."""

    ruoli_ammessi = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA})
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/deleghe_zona.html"
    context_object_name = "deleghe"

    def get_queryset(self):
        return Delega.objects.select_related("ruolo", "delegante", "delegato").all()


class DelegaCreaView(RuoloRequiredMixin, FormView):
    template_name = "accounts/delega_crea.html"
    form_class = DelegaForm
    success_url = reverse_lazy("accounts:deleghe_lista")

    def test_func(self) -> bool:
        return self.request.user.is_authenticated

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["ruoli_delegabili"] = Ruolo.objects.filter(utente=self.request.user, attivo=True)
        return kwargs

    def form_valid(self, form):
        deleghe_service.crea_delega(
            delegante=self.request.user,
            ruolo=form.cleaned_data["ruolo"],
            email_delegato=form.cleaned_data["email_delegato"],
            data_fine=form.cleaned_data["data_fine"],
            note=form.cleaned_data.get("note", ""),
        )
        messages.success(self.request, "Delega creata.")
        return super().form_valid(form)


class DelegaRevocaView(RuoloRequiredMixin, View):
    def test_func(self) -> bool:
        return self.request.user.is_authenticated

    def post(self, request, pk):
        delega = Delega.objects.select_related("ruolo").get(pk=pk)
        e_titolare = delega.delegante_id == request.user.id
        e_segreteria = any(
            r.tipo in {Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA} and not r.is_delega
            for r in ruoli_effettivi(request.user)
        )
        if not (e_titolare or e_segreteria):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        deleghe_service.revoca_delega(delega, revocata_da=request.user)
        messages.success(request, "Delega revocata.")
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("accounts:deleghe_lista"))


class RuoloListaView(RuoloRequiredMixin, ListView):
    """Ruoli amministrativi espliciti (D-35): unico punto applicativo da cui
    revocarli, per non lasciare Django admin come unica via (senza cascata su
    deleghe/CG derivato)."""

    ruoli_ammessi = ruoli_service.RUOLI_GESTIONE_RUOLI
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/ruolo_lista.html"
    context_object_name = "ruoli"

    def get_queryset(self):
        return (
            Ruolo.objects.filter(origine=Ruolo.Origine.AMMINISTRATIVO, attivo=True)
            .select_related("utente", "gruppo")
            .order_by("tipo", "utente__email")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # M10: "Nuovo invito"/"Storico inviti" hanno un perimetro più fine di
        # quello (RUOLI_GESTIONE_RUOLI) che dà accesso a questa pagina.
        tipi_diretti = {r.tipo for r in ruoli_effettivi(self.request.user) if not r.is_delega}
        ctx["puo_invitare"] = bool(tipi_diretti & RUOLI_INVITO_DIRETTO)
        ctx["puo_vedere_inviti"] = bool(tipi_diretti & RUOLI_CHE_INVITANO)
        return ctx


class RuoloRevocaView(RuoloRequiredMixin, View):
    ruoli_ammessi = ruoli_service.RUOLI_GESTIONE_RUOLI
    ruoli_ammessi_solo_diretti = True

    def post(self, request, pk):
        ruolo = Ruolo.objects.select_related("utente").get(pk=pk)
        ruoli_service.revoca_ruolo_esplicito(utente=request.user, ruolo=ruolo)
        messages.success(request, f"Ruolo revocato: {ruolo}.")
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("accounts:ruolo_lista"))


class RuoloAssegnaCercaView(BreadcrumbExtraMixin, RuoloRequiredMixin, ListView):
    """Ricerca dell'utente a cui assegnare un ruolo diretto, senza invito
    (M11). Stesso pattern di ricerca di `ImpersonaListaView` (decisione
    presa): niente elenco sfogliabile senza query."""

    ruoli_ammessi = ruoli_service.RUOLI_GESTIONE_RUOLI
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/ruolo_assegna_cerca.html"
    context_object_name = "risultati"
    paginate_by = 20

    @classmethod
    def breadcrumb_extra(cls, request):
        return [
            {"label": "Amministrazione"},
            {"label": "Ruoli", "url": reverse_lazy("accounts:ruolo_lista")},
            {"label": "Assegna ruolo"},
        ]

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        if not query:
            return Utente.objects.none()
        return Utente.objects.filter(
            Q(email__icontains=query)
            | Q(username__icontains=query)
            | Q(codice_socio__icontains=query)
        ).order_by("email")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["query"] = self.request.GET.get("q", "").strip()
        return ctx


class RuoloAssegnaView(BreadcrumbExtraMixin, RuoloRequiredMixin, View):
    """Secondo passo di M11: assegna un ruolo (mai CG) all'utente scelto
    nella ricerca, sul modello di RicercaCapoView → AssegnaIncaricoView
    (`?utente_id=`, come `?codice_socio=`)."""

    ruoli_ammessi = ruoli_service.RUOLI_GESTIONE_RUOLI
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/ruolo_assegna.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return [
            {"label": "Amministrazione"},
            {"label": "Ruoli", "url": reverse_lazy("accounts:ruolo_lista")},
            {"label": "Assegna ruolo"},
        ]

    def get(self, request):
        utente_destinatario = get_object_or_404(Utente, pk=request.GET.get("utente_id"))
        form = RuoloAssegnaForm()
        return render(
            request,
            self.template_name,
            {"form": form, "utente_destinatario": utente_destinatario},
        )

    def post(self, request):
        utente_destinatario = get_object_or_404(Utente, pk=request.POST.get("utente_id"))
        form = RuoloAssegnaForm(request.POST)
        contesto = {"form": form, "utente_destinatario": utente_destinatario}
        if not form.is_valid():
            return render(request, self.template_name, contesto)
        try:
            ruoli_service.crea_ruolo_esplicito(
                utente_assegnante=request.user,
                utente_destinatario=utente_destinatario,
                tipo=form.cleaned_data["tipo"],
                branca=form.cleaned_data["branca"],
                settore=form.cleaned_data["settore"],
                data_fine=form.cleaned_data["data_fine"],
            )
        except (PermissionDenied, ValidationError, ValueError) as exc:
            form.add_error(None, messaggio_utente(exc))
            return render(request, self.template_name, contesto)
        messages.success(request, f"Ruolo assegnato a {utente_destinatario}.")
        return redirect(reverse_lazy("accounts:ruolo_lista"))


class VistaDiProvaView(RuoloRequiredMixin, View):
    """D-27: vista di prova per ruolo, in sola lettura — imposta/rimuove un
    flag di sessione letto solo dalle view che ne fanno esplicita richiesta,
    mai da ruoli_effettivi()/gruppi_visibili()."""

    ruoli_ammessi = frozenset({Ruolo.Tipo.ADMIN})
    ruoli_ammessi_solo_diretti = True

    def post(self, request):
        ruolo = request.POST.get("ruolo") or None
        if ruolo:
            request.session["ruolo_di_prova"] = ruolo
        else:
            request.session.pop("ruolo_di_prova", None)
        return redirect(request.META.get("HTTP_REFERER") or reverse_lazy("core:home"))


class ImpersonaListaView(RuoloRequiredMixin, ListView):
    """Elenco/ricerca dell'utente da impersonare (D-27). Il perimetro non è
    `ruoli_ammessi` ma `puo_impersonare_qualcuno()`, la stessa funzione usata
    per l'HIJACK_PERMISSION_CHECK: un ADMIN per delega o senza ruolo diretto
    non deve vedere né questa pagina né il bottone di hijack.

    M12, deviazione dichiarata dal principio "niente elenco sfogliabile" di
    D-34: senza query mostra l'elenco completo (paginato), non
    `Utente.objects.none()`. Qui il bersaglio è un elenco di account
    piattaforma, non l'anagrafica soci (nessun dato di minori/recapiti), e la
    pagina resta comunque riservata a chi supera `puo_impersonare_qualcuno()`
    (oggi solo ADMIN diretto), il livello di privilegio più alto del
    sistema."""

    template_name = "accounts/impersona_lista.html"
    context_object_name = "risultati"
    paginate_by = 20

    def test_func(self) -> bool:
        # LoginRequiredMixin garantisce l'autenticazione prima di test_func().
        assert isinstance(self.request.user, Utente)
        return puo_impersonare_qualcuno(self.request.user)

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        qs = Utente.objects.exclude(pk=self.request.user.pk).order_by("email")
        if not query:
            return qs
        return qs.filter(
            Q(email__icontains=query)
            | Q(username__icontains=query)
            | Q(codice_socio__icontains=query)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["query"] = self.request.GET.get("q", "").strip()
        return ctx
