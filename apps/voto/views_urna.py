"""Pagine pubbliche del voto, senza login (docs/plan_voto.md, flusso 2).

- Il codice arriva dal link nel fragment (`/voto/#c=…`, mai nei log del
  server) o digitato a mano, e si manda solo in POST. In sessione resta l'id
  del `CodiceVoto`, mai il codice in chiaro.
- Tentativi limitati per sessione, non per IP: in sala 200 telefoni escono
  dallo stesso NAT.
- Nessuna pagina va in cache; nessun log registra codici, ricevute o scelte.
- Durante la votazione si vede solo la propria scheda: mai risultati parziali."""

from __future__ import annotations

import time

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from apps.assemblee.models import Votazione
from apps.assemblee.votazioni import frase_esito

from . import postazioni, scrutinio, urna
from .models import CodiceVoto, Postazione

SESSIONE_CODICE = "voto_codice"
SESSIONE_TENTATIVI = "voto_tentativi"
MAX_TENTATIVI = 10
# Al seggio la sessione è condivisa da tutti i votanti che passano.
MAX_TENTATIVI_SEGGIO = 30
SECONDI_RICEVUTA_SEGGIO = 30
SALE_COOKIE = "apps.voto.postazione"


def postazione_della_richiesta(request: HttpRequest) -> Postazione | None:
    valore = request.get_signed_cookie(postazioni.COOKIE, default=None, salt=SALE_COOKIE)
    return postazioni.dal_cookie(valore)


FINESTRA_TENTATIVI = 15 * 60
CACHE_STATO_SECONDI = 2


def _tentativi_recenti(request: HttpRequest) -> list[float]:
    ora = time.time()
    return [t for t in request.session.get(SESSIONE_TENTATIVI, []) if ora - t < FINESTRA_TENTATIVI]


def codice_della_sessione(request: HttpRequest) -> CodiceVoto | None:
    codice_id = request.session.get(SESSIONE_CODICE)
    if codice_id is None:
        return None
    codice = (
        CodiceVoto.objects.filter(pk=codice_id, revocato_il__isnull=True)
        .select_related("seduta__assemblea", "avente")
        .first()
    )
    if not urna.codice_valido(codice):
        request.session.pop(SESSIONE_CODICE, None)
        return None
    return codice


@method_decorator(never_cache, name="dispatch")
class UrnaView(View):
    """Accesso con il codice. Con una sessione già aperta porta alla scheda."""

    template_name = "voto/urna.html"

    def get(self, request):
        if codice_della_sessione(request) is not None:
            return redirect("voto:scheda")
        return render(
            request, self.template_name, {"postazione": postazione_della_richiesta(request)}
        )


@method_decorator(never_cache, name="dispatch")
class AccediView(View):
    def get(self, request):
        return redirect("voto:urna")

    def post(self, request):
        postazione = postazione_della_richiesta(request)
        tentativi = _tentativi_recenti(request)
        if len(tentativi) >= (MAX_TENTATIVI_SEGGIO if postazione else MAX_TENTATIVI):
            messages.error(request, "Troppi tentativi con codici non validi: chiedi al banco.")
            return redirect("voto:urna")
        codice = urna.accedi(request.POST.get("codice", ""))
        if codice is not None and not urna.ammesso_da(codice, postazione):
            messages.error(request, "In questa assemblea si vota solo ai seggi in sala.")
            return redirect("voto:urna")
        if codice is None:
            request.session[SESSIONE_TENTATIVI] = [*tentativi, time.time()]
            messages.error(request, "Codice non valido o non più attivo. Controllalo e riprova.")
            return redirect("voto:urna")
        # Nuova chiave di sessione all'accesso, come a un login (non al seggio,
        # dove la sessione serve a contare i tentativi della postazione).
        if postazione is None:
            request.session.cycle_key()
        request.session[SESSIONE_CODICE] = codice.pk
        request.session.pop(SESSIONE_TENTATIVI, None)
        return redirect("voto:scheda")


def _scelte_dal_post(request: HttpRequest, numero: int) -> list[urna.Scelte]:
    scelte = []
    for indice in range(numero):
        try:
            candidati = tuple(int(v) for v in request.POST.getlist(f"candidati_{indice}"))
        except ValueError:
            raise ValidationError("Scelta non valida.") from None
        scelte.append(
            urna.Scelte(
                esito=request.POST.get(f"esito_{indice}", urna.ESITO_VOTO),
                candidati=candidati,
                liberi=tuple(request.POST.getlist(f"liberi_{indice}")),
            )
        )
    return scelte


def _riepilogo(votazione: Votazione, scelte: urna.Scelte) -> list[str]:
    """Righe leggibili di una scheda, per il riepilogo e la ricevuta."""
    if scelte.esito == urna.ESITO_BIANCA:
        return ["Scheda bianca"]
    if scelte.esito == urna.ESITO_NULLA:
        return ["Scheda annullata (nulla)"]
    nomi = dict(votazione.candidati.values_list("pk", "nome"))
    righe = [nomi[c] for c in scelte.candidati]
    righe += [f"«{nome}» (nome scritto)" for nome in scelte.liberi]
    return righe


@method_decorator(never_cache, name="dispatch")
class SchedaView(View):
    """La scheda della votazione aperta, oppure l'attesa con il polling.
    POST in due passi: «rivedi» mostra il riepilogo, «conferma» vota."""

    def _contesto(self, codice: CodiceVoto) -> dict:
        votazione = urna.votazione_aperta(codice.seduta)
        spettanti = []
        if votazione is not None and urna.votazioni_in_app(votazione):
            spettanti = urna.schede_spettanti(codice, votazione)
        else:
            votazione = None
        return {
            "codice": codice,
            "assemblea": codice.seduta.assemblea,
            "seduta": codice.seduta,
            "votazione": votazione,
            "candidati": list(votazione.candidati.all()) if votazione else [],
            "spettanti": spettanti,
            "posti": range(votazione.posti) if votazione else range(0),
        }

    def get(self, request):
        codice = codice_della_sessione(request)
        if codice is None:
            return redirect("voto:urna")
        return render(request, "voto/scheda.html", self._contesto(codice))

    def post(self, request):
        codice = codice_della_sessione(request)
        if codice is None:
            return redirect("voto:urna")
        contesto = self._contesto(codice)
        votazione = contesto["votazione"]
        if votazione is None or str(votazione.pk) != request.POST.get("votazione"):
            messages.warning(request, "La votazione è cambiata: ricontrolla la scheda.")
            return redirect("voto:scheda")
        azione = request.POST.get("azione")
        postazione = postazione_della_richiesta(request)
        try:
            scelte = _scelte_dal_post(request, len(contesto["spettanti"]))
            if azione == "conferma":
                esito = urna.vota(codice.pk, votazione, scelte, postazione)
            else:
                scelte = [urna.valida_scelte(votazione, s) for s in scelte]
        except ValidationError as errore:
            contesto["errore"] = " ".join(errore.messages)
            return render(request, "voto/scheda.html", contesto)
        if azione == "conferma":
            ricevute = [
                {
                    "ricevuta": r.ricevuta,
                    "per_delega_di": r.per_delega_di,
                    "righe": _riepilogo(votazione, r.scelte),
                }
                for r in esito.ricevute
            ]
            al_seggio = postazione is not None
            if al_seggio:
                # Il prossimo votante non deve trovare la sessione di chi ha appena votato.
                request.session.pop(SESSIONE_CODICE, None)
            return render(
                request,
                "voto/ricevuta.html",
                {
                    **contesto,
                    "ricevute": ricevute,
                    "votazione": votazione,
                    "al_seggio": al_seggio,
                    "secondi_ricevuta": SECONDI_RICEVUTA_SEGGIO,
                },
            )
        schede = [
            {
                "indice": indice,
                "spettante": spettante,
                "scelte": scelta,
                "righe": _riepilogo(votazione, scelta),
            }
            for indice, (spettante, scelta) in enumerate(
                zip(contesto["spettanti"], scelte, strict=True)
            )
        ]
        return render(request, "voto/riepilogo.html", {**contesto, "schede": schede})


@method_decorator(never_cache, name="dispatch")
class StatoView(View):
    """Polling della pagina di attesa: solo l'id della votazione aperta,
    condiviso per seduta in cache per qualche secondo (il carico vero del voto)."""

    def get(self, request):
        codice = codice_della_sessione(request)
        if codice is None:
            return JsonResponse({"accesso": False})
        chiave = f"voto:stato:{codice.seduta_id}"
        votazione_id = cache.get(chiave, "assente")
        if votazione_id == "assente":
            votazione = urna.votazione_aperta(codice.seduta)
            votazione_id = votazione.pk if votazione else None
            cache.set(chiave, votazione_id, CACHE_STATO_SECONDI)
        return JsonResponse({"accesso": True, "votazione": votazione_id})


class EsciView(View):
    def post(self, request):
        request.session.flush()
        return redirect(reverse("voto:urna"))


class BachecaView(View):
    """Bacheca pubblica di una votazione, a risultati registrati: ricevuta →
    scheda interpretata, con l'impronta riportata nel verbale."""

    def get(self, request, votazione_pk):
        votazione = get_object_or_404(
            Votazione.objects.select_related("seduta__assemblea"),
            pk=votazione_pk,
            chiusa_il__isnull=False,
            aperta_in_app_il__isnull=False,
        )
        righe = scrutinio.righe_bacheca(votazione)
        return render(
            request,
            "voto/bacheca.html",
            {
                "votazione": votazione,
                "assemblea": votazione.seduta.assemblea,
                "righe": righe,
                "impronta": scrutinio.impronta(righe),
                "frase_esito": frase_esito(votazione),
            },
        )


@method_decorator(never_cache, name="dispatch")
class VerificaView(View):
    """Verifica personale della ricevuta. Tentativi limitati come l'accesso."""

    template_name = "voto/verifica.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        tentativi = _tentativi_recenti(request)
        if len(tentativi) >= MAX_TENTATIVI:
            messages.error(request, "Troppi tentativi: riprova più tardi.")
            return redirect("voto:verifica")
        esito = scrutinio.verifica_ricevuta(request.POST.get("ricevuta", ""))
        if not esito.trovata:
            request.session[SESSIONE_TENTATIVI] = [*tentativi, time.time()]
        return render(request, self.template_name, {"esito": esito})


@method_decorator(never_cache, name="dispatch")
class AttivaPostazioneView(View):
    """Link monouso aperto sul tablet del seggio: lascia il cookie firmato."""

    def get(self, request, segreto):
        return render(request, "voto/postazione_attiva.html", {"segreto": segreto})

    def post(self, request, segreto):
        risultato = postazioni.attiva(segreto)
        if risultato is None:
            return render(request, "voto/postazione_attiva.html", {"non_valido": True})
        postazione, valore = risultato
        request.session.flush()
        risposta = redirect("voto:urna")
        risposta.set_signed_cookie(
            postazioni.COOKIE,
            valore,
            salt=SALE_COOKIE,
            max_age=24 * 3600,
            httponly=True,
            samesite="Strict",
            secure=request.is_secure(),
        )
        return risposta
