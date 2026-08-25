from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.accounts.mixins import RuoloRequiredMixin
from apps.accounts.models import Ruolo

from .forms import ImpostazioniPiattaformaForm, TemplateEmailForm
from .invio_email import invia_email_template, sanifica_html
from .mixins import BreadcrumbExtraMixin
from .models import ImpostazioniPiattaforma, TemplateEmail
from .template_email import CONTESTO_ESEMPIO, VARIABILI_PER_CODICE, sostituisci_placeholder

RUOLI_GESTIONE_IMPOSTAZIONI = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "core/home.html"


class ImpostazioniPiattaformaView(RuoloRequiredMixin, View):
    # D-11: stesso perimetro dei parametri di campagna, esclusi i delegati.
    ruoli_ammessi = RUOLI_GESTIONE_IMPOSTAZIONI
    ruoli_ammessi_solo_diretti = True
    template_name = "core/impostazioni.html"

    def get(self, request):
        form = ImpostazioniPiattaformaForm(instance=ImpostazioniPiattaforma.corrente())
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ImpostazioniPiattaformaForm(
            request.POST, instance=ImpostazioniPiattaforma.corrente()
        )
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        form.save()
        messages.success(request, "Impostazioni aggiornate.")
        return redirect(reverse("core:impostazioni"))


class TemplateEmailListaView(BreadcrumbExtraMixin, RuoloRequiredMixin, ListView):
    ruoli_ammessi = RUOLI_GESTIONE_IMPOSTAZIONI
    ruoli_ammessi_solo_diretti = True
    template_name = "core/template_email_lista.html"
    context_object_name = "template_email"

    @classmethod
    def breadcrumb_extra(cls, request):
        return [
            {"label": "Amministrazione"},
            {"label": "Impostazioni", "url": reverse("core:impostazioni")},
            {"label": "Template email"},
        ]

    def get_queryset(self):
        return TemplateEmail.objects.all()


class TemplateEmailModificaView(BreadcrumbExtraMixin, RuoloRequiredMixin, View):
    """Anteprima e invio di test (M8.4) riusano lo stesso motore di
    sostituzione/sanitizzazione di `invia_email_template` — nessun percorso
    di invio parallelo. `codice` non è mai modificabile da qui (M8.1)."""

    ruoli_ammessi = RUOLI_GESTIONE_IMPOSTAZIONI
    ruoli_ammessi_solo_diretti = True
    template_name = "core/template_email_modifica.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return [
            {"label": "Amministrazione"},
            {"label": "Impostazioni", "url": reverse("core:impostazioni")},
            {"label": "Template email", "url": reverse("core:template_email_lista")},
            {"label": "Modifica template"},
        ]

    def _contesto_pagina(self, template: TemplateEmail, form: TemplateEmailForm, **extra) -> dict:
        contesto = {
            "template": template,
            "form": form,
            "variabili": VARIABILI_PER_CODICE.get(template.codice, []),
        }
        contesto.update(extra)
        return contesto

    def get(self, request, pk):
        template = get_object_or_404(TemplateEmail, pk=pk)
        form = TemplateEmailForm(instance=template)
        return render(request, self.template_name, self._contesto_pagina(template, form))

    def post(self, request, pk):
        template = get_object_or_404(TemplateEmail, pk=pk)
        form = TemplateEmailForm(request.POST, instance=template)
        azione = request.POST.get("azione", "salva")

        if not form.is_valid():
            return render(request, self.template_name, self._contesto_pagina(template, form))

        contesto_esempio = CONTESTO_ESEMPIO.get(template.codice, {})

        if azione == "anteprima":
            anteprima = {
                "oggetto": sostituisci_placeholder(form.cleaned_data["oggetto"], contesto_esempio),
                "corpo_testo": sostituisci_placeholder(
                    form.cleaned_data["corpo_testo"], contesto_esempio
                ),
                "corpo_html": sanifica_html(
                    sostituisci_placeholder(form.cleaned_data["corpo_html"], contesto_esempio)
                ),
            }
            return render(
                request,
                self.template_name,
                self._contesto_pagina(template, form, anteprima=anteprima),
            )

        form.save()

        if azione == "test":
            invia_email_template(
                codice_template=template.codice,
                destinatari=[request.user.email],
                contesto=contesto_esempio,
            )
            messages.success(request, f"Email di test inviata a {request.user.email}.")
        else:
            messages.success(request, "Template aggiornato.")
        return redirect(reverse("core:template_email_modifica", args=[template.pk]))
