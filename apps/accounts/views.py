from axes.decorators import axes_dispatch
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from apps.organizzazione.models import Gruppo

from . import deleghe as deleghe_service
from . import inviti as inviti_service
from .forms import AttivazioneForm, DelegaForm, InvitoSingoloForm, RecuperoOtpForm
from .mixins import RuoloRequiredMixin
from .models import Delega, InvitoAttivazione, Ruolo
from .permessi import ruoli_effettivi

RUOLI_CHE_INVITANO = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


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


class InvitoCreaView(RuoloRequiredMixin, FormView):
    """Invio di un singolo invito OTP (D-20). Perimetro: ADMIN, SEGRETERIA, RDZ."""

    ruoli_ammessi = RUOLI_CHE_INVITANO
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/invito_crea.html"
    form_class = InvitoSingoloForm
    success_url = reverse_lazy("accounts:invito_lista")

    def form_valid(self, form):
        gruppo = None
        codice = form.cleaned_data.get("gruppo")
        if codice:
            gruppo = Gruppo.objects.filter(codice=codice).first()
            if gruppo is None:
                form.add_error("gruppo", "Nessun gruppo con questo codice.")
                return self.form_invalid(form)
        inviti_service.crea_invito(
            email=form.cleaned_data["email"],
            creato_da=self.request.user,
            gruppo=gruppo,
            ruolo_proposto=form.cleaned_data.get("ruolo_proposto") or None,
        )
        messages.success(self.request, f"Invito inviato a {form.cleaned_data['email']}.")
        return super().form_valid(form)


class InvitoListaView(RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_CHE_INVITANO
    ruoli_ammessi_solo_diretti = True
    template_name = "accounts/invito_lista.html"
    context_object_name = "inviti"
    paginate_by = 50

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
