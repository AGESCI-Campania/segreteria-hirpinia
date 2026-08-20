from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.mixins import RuoloRequiredMixin
from apps.accounts.models import Ruolo

from .forms import ImpostazioniPiattaformaForm
from .models import ImpostazioniPiattaforma

RUOLI_GESTIONE_IMPOSTAZIONI = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


class HomeView(TemplateView):
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
