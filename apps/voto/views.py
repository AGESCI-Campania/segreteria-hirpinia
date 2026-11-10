from __future__ import annotations

import segno
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.cache import never_cache

from apps.assemblee import elenco
from apps.assemblee.models import Assemblea, AventeDiritto, Seduta
from apps.assemblee.permessi import assemblee_visibili

from . import codici, sistema

MESSAGGI_INVIO = {
    codici.EsitoInvio.INVIATO: "codice di voto inviato per email",
    codici.EsitoInvio.GIA_ATTIVO: "ha già un codice di voto per questa seduta",
    codici.EsitoInvio.SENZA_EMAIL: "non ha un'email: inseriscila o mostra il codice al banco",
    codici.EsitoInvio.INVIO_FALLITO: "invio del codice non riuscito: riprova o mostra il codice",
}


def messaggio_invio(request, avente: AventeDiritto, esito: codici.EsitoInvio) -> None:
    """Esito dell'invio al banco, in un solo punto per presenze e codici."""
    testo = MESSAGGI_INVIO.get(esito)
    if testo is None:
        return
    livello = (
        messages.success
        if esito in (codici.EsitoInvio.INVIATO, codici.EsitoInvio.GIA_ATTIVO)
        else messages.warning
    )
    livello(request, f"{avente}: {testo}.")


def _seduta_e_avente(request, pk: int, seduta_pk: int, avente_pk: int):
    assemblea = get_object_or_404(assemblee_visibili(request.user), pk=pk)
    seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea=assemblea)
    avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea=assemblea)
    return seduta, avente


def _torna(request, seduta: Seduta):
    destinazione = request.POST.get("next", "")
    if destinazione and url_has_allowed_host_and_scheme(
        destinazione, allowed_hosts={request.get_host()}
    ):
        return redirect(destinazione)
    return redirect(reverse("assemblee:presenze", args=[seduta.assemblea_id, seduta.pk]))


class CodiceInviaView(LoginRequiredMixin, View):
    """Invia (o reinvia) il codice per email; se arriva un'email dal banco la
    salva prima sull'avente."""

    def post(self, request, pk, seduta_pk, avente_pk):
        seduta, avente = _seduta_e_avente(request, pk, seduta_pk, avente_pk)
        try:
            email = request.POST.get("email", "").strip()
            if email:
                elenco.aggiorna_email(avente, email, request.user)
            messaggio_invio(request, avente, codici.invia(seduta, avente, request.user))
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return _torna(request, seduta)


@method_decorator(never_cache, name="dispatch")
class CodiceMostraView(LoginRequiredMixin, View):
    """«Rigenera e mostra»: revoca il codice attivo e mostra il nuovo una sola
    volta, in chiaro e come QR, su una pagina autonoma stampabile. Solo POST:
    ricaricare la pagina non rigenera nulla e il codice non si rilegge."""

    template_name = "voto/codice_mostra.html"

    def get(self, request, pk, seduta_pk, avente_pk):
        return redirect(reverse("assemblee:presenze", args=[pk, seduta_pk]))

    def post(self, request, pk, seduta_pk, avente_pk):
        seduta, avente = _seduta_e_avente(request, pk, seduta_pk, avente_pk)
        try:
            codice = codici.emetti(seduta, avente, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
            return _torna(request, seduta)
        link = codici.link_urna(codice)
        contesto = {
            "seduta": seduta,
            "assemblea": seduta.assemblea,
            "avente": avente,
            "codice": codici.formatta(codice),
            "qr": segno.make(link, error="m").svg_inline(scale=6, dark="#000", light="#fff"),
            "torna": request.POST.get("next")
            or reverse("assemblee:presenze", args=[pk, seduta_pk]),
        }
        return render(request, self.template_name, contesto)


class SistemaVotoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        try:
            if "sistema_voto" in request.POST:
                sistema.imposta_sistema(assemblea, request.POST["sistema_voto"], request.user)
            if "modalita_voto" in request.POST:
                assemblea.refresh_from_db()
                if assemblea.voto_catello:
                    sistema.imposta_modalita(assemblea, request.POST["modalita_voto"], request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, "Sistema di voto aggiornato.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))


class UrnaView(View):
    """Pagina pubblica di voto: senza login, il codice arriva nel fragment."""

    template_name = "voto/urna.html"

    def get(self, request):
        return render(request, self.template_name)
