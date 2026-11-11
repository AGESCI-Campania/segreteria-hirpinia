from __future__ import annotations

import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.cache import never_cache

from apps.assemblee import elenco
from apps.assemblee.models import Assemblea, AventeDiritto, Seduta, Votazione
from apps.assemblee.permessi import assemblee_visibili, puo_operare
from apps.core.mixins import BreadcrumbExtraMixin

from . import codici, etichetta, postazioni, scrutinio, sistema

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
        dati_etichetta = etichetta.Etichetta(
            codice=codici.formatta(codice),
            link=link,
            nome=f"{avente.nome} {avente.cognome}",
            assemblea=str(seduta.assemblea),
            convocazione=f"{seduta.get_convocazione_display()} del {seduta.data:%d/%m/%Y}",
        )
        contesto = {
            "seduta": seduta,
            "assemblea": seduta.assemblea,
            "avente": avente,
            "codice": codici.formatta(codice),
            # Immagine data: invece di SVG inline, così il template non usa |safe.
            "qr": segno.make(link, error="m").svg_data_uri(scale=6, dark="#000", light="#fff"),
            # Etichetta 50×80 mm già pronta nella pagina, come file da scaricare:
            # il codice non passa da un'altra richiesta (etichetta.py).
            "etichetta_png": etichetta.data_uri(etichetta.png(dati_etichetta), "image/png"),
            "etichetta_pdf": etichetta.data_uri(etichetta.pdf(dati_etichetta), "application/pdf"),
            "torna": _torna(request, seduta).url,
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


def _votazione(request, pk: int, seduta_pk: int, votazione_pk: int) -> Votazione:
    assemblea = get_object_or_404(assemblee_visibili(request.user), pk=pk)
    return get_object_or_404(
        Votazione, pk=votazione_pk, seduta_id=seduta_pk, seduta__assemblea=assemblea
    )


def _alla_votazione(votazione: Votazione):
    return redirect(
        reverse(
            "assemblee:votazione",
            args=[votazione.seduta.assemblea_id, votazione.seduta_id, votazione.pk],
        )
    )


class UrnaAzioneView(LoginRequiredMixin, View):
    """Apertura e chiusura dell'urna elettronica dalla pagina della votazione."""

    def post(self, request, pk, seduta_pk, votazione_pk):
        votazione = _votazione(request, pk, seduta_pk, votazione_pk)
        azione = request.POST.get("azione")
        try:
            if azione == "apri":
                scrutinio.apri_urna(votazione, request.user)
                messages.success(request, "Urna aperta: si vota dal telefono e ai seggi.")
            elif azione == "chiudi" and request.POST.get("conferma") == "1":
                # Le urne aperte della seduta si chiudono tutte insieme.
                chiuse = scrutinio.chiudi_urne(votazione.seduta, request.user)
                messages.success(
                    request,
                    (
                        "Urna chiusa: le schede sono state rimescolate."
                        if len(chiuse) == 1
                        else f"{len(chiuse)} urne chiuse: le schede sono state rimescolate."
                    ),
                )
            else:
                messages.error(request, "Azione non riconosciuta o non confermata.")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return _alla_votazione(votazione)


class ApriUrneView(LoginRequiredMixin, View):
    """Apertura insieme delle urne scelte nell'elenco delle votazioni della
    seduta (permessi e regole in scrutinio.apri_urne())."""

    def post(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        scelte = request.POST.getlist("votazioni")
        votazioni = list(
            Votazione.objects.filter(seduta=seduta, pk__in=[v for v in scelte if v.isdigit()])
        )
        try:
            scrutinio.apri_urne(seduta, votazioni, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(
                request,
                (
                    "Urna aperta: si vota dal telefono e ai seggi."
                    if len(votazioni) == 1
                    else f"{len(votazioni)} urne aperte: chi vota le trova tutte nella stessa pagina."
                ),
            )
        return redirect(reverse("assemblee:votazioni", args=[pk, seduta_pk]))


class NomiScrittiView(LoginRequiredMixin, BreadcrumbExtraMixin, View):
    """La commissione elettorale attribuisce i nomi scritti a un avente
    diritto o li dichiara nulli. Il testo si vede solo qui."""

    template_name = "voto/nomi_scritti.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        kwargs = request.resolver_match.kwargs
        return [
            {"label": "Moduli"},
            {"label": "Assemblee", "url": reverse("assemblee:assemblea_lista")},
            {
                "label": "Votazione",
                "url": reverse(
                    "assemblee:votazione",
                    args=[kwargs["pk"], kwargs["seduta_pk"], kwargs["votazione_pk"]],
                ),
            },
            {"label": "Nomi scritti"},
        ]

    def _contesto(self, votazione: Votazione) -> dict:
        return {
            "votazione": votazione,
            "assemblea": votazione.seduta.assemblea,
            "seduta": votazione.seduta,
            "nomi": scrutinio.nomi_scritti(votazione),
            "aventi": votazione.seduta.assemblea.aventi_diritto.nell_elenco().order_by(
                "cognome", "nome"
            ),
        }

    def get(self, request, pk, seduta_pk, votazione_pk):
        votazione = _votazione(request, pk, seduta_pk, votazione_pk)
        if not puo_operare(request.user, votazione.seduta.assemblea):
            raise PermissionDenied
        return render(request, self.template_name, self._contesto(votazione))

    def post(self, request, pk, seduta_pk, votazione_pk):
        votazione = _votazione(request, pk, seduta_pk, votazione_pk)
        scelta = request.POST.get("avente", "")
        avente = None
        if scelta and scelta != "nullo":
            avente = get_object_or_404(
                AventeDiritto, pk=scelta, assemblea_id=votazione.seduta.assemblea_id
            )
        if not scelta:
            messages.error(request, "Scegli un avente diritto oppure «nullo».")
        else:
            try:
                scrutinio.interpreta(votazione, request.POST.get("testo", ""), avente, request.user)
            except ValidationError as errore:
                messages.error(request, " ".join(errore.messages))
        return redirect(reverse("voto:nomi_scritti", args=[pk, seduta_pk, votazione_pk]))


@method_decorator(never_cache, name="dispatch")
class SeggiView(LoginRequiredMixin, BreadcrumbExtraMixin, View):
    """Postazioni di voto della seduta: creazione (il link di attivazione si
    vede una volta sola) e disattivazione."""

    template_name = "voto/seggi.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        kwargs = request.resolver_match.kwargs
        return [
            {"label": "Moduli"},
            {"label": "Assemblee", "url": reverse("assemblee:assemblea_lista")},
            {
                "label": "Seduta",
                "url": reverse("assemblee:seduta", args=[kwargs["pk"], kwargs["seduta_pk"]]),
            },
            {"label": "Seggi"},
        ]

    def _seduta(self, request, pk, seduta_pk) -> Seduta:
        assemblea = get_object_or_404(assemblee_visibili(request.user), pk=pk)
        if not puo_operare(request.user, assemblea):
            raise PermissionDenied
        return get_object_or_404(Seduta, pk=seduta_pk, assemblea=assemblea)

    def _contesto(self, seduta: Seduta, **extra) -> dict:
        return {
            "seduta": seduta,
            "assemblea": seduta.assemblea,
            "postazioni": seduta.postazioni.all(),
            **extra,
        }

    def get(self, request, pk, seduta_pk):
        seduta = self._seduta(request, pk, seduta_pk)
        return render(request, self.template_name, self._contesto(seduta))

    def post(self, request, pk, seduta_pk):
        seduta = self._seduta(request, pk, seduta_pk)
        extra: dict = {}
        try:
            if "disattiva" in request.POST:
                postazione = get_object_or_404(seduta.postazioni, pk=request.POST.get("disattiva"))
                postazioni.disattiva(postazione, request.user)
                messages.success(request, f"{postazione} disattivata.")
            else:
                postazione, segreto = postazioni.crea(
                    seduta, request.POST.get("nome", ""), request.user
                )
                # Stessa convenzione dei link nelle email: SITE_URL, mai build_absolute_uri.
                link = f"{settings.SITE_URL}{reverse('voto:attiva_postazione')}#s={segreto}"
                extra = {
                    "nuova": postazione,
                    "link": link,
                    "qr": segno.make(link, error="m").svg_data_uri(scale=5),
                }
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return render(request, self.template_name, self._contesto(seduta, **extra))
