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
from apps.core.email import mailpit_api
from apps.core.mixins import BreadcrumbExtraMixin
from apps.organizzazione.models import Gruppo
from apps.voto import codici as codici_voto
from apps.voto import scrutinio as scrutinio_voto
from apps.voto import urna as urna_voto
from apps.voto import views as voto_banco

from . import (
    candidature,
    comitato,
    cruscotto,
    duplica,
    elenco,
    email_aventi,
    odg,
    presidenza,
    prova,
    sedute,
)
from . import deleghe as deleghe_ae
from . import file as file_assemblea
from . import quorum as quorum_assemblea
from . import verbale as verbale_assemblea
from . import votazioni as voto
from .forms import (
    AggiungiGruppoForm,
    AssembleaCreaForm,
    AssembleaNuovaForm,
    AventeInserisciForm,
    CandidaturaForm,
    ComitatoAggiungiForm,
    ConvocazioneForm,
    DelegaForm,
    DiscussioneForm,
    EmailAventeForm,
    ImportEmailForm,
    IncaricoDichiaratoFormSet,
    PosizioneForm,
    PuntoOdGForm,
    QualificheForm,
    TitoloAssembleaForm,
    TrasferisciForm,
    VariazioneRappresentanteForm,
    VerbaleForm,
    VotazioneForm,
    form_risultati,
)
from .models import (
    Assemblea,
    AventeDiritto,
    CanaleVoto,
    Candidatura,
    DelegaAE,
    ImportazioneEmail,
    IncaricoAssemblea,
    ModalitaVoto,
    OperatoreVoto,
    PosizioneVoto,
    PuntoOdG,
    RichiedenteVerifica,
    RuoloAssemblea,
    Seduta,
    SistemaVoto,
    TipoAppello,
    Votazione,
)
from .permessi import (
    accede_assemblee,
    assemblee_visibili,
    puo_compilare_verbale,
    puo_gestire_assemblee,
    puo_operare,
    puo_vedere_odg,
)
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


class CompilaVerbaleMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Verbale dell'assemblea: gestori, presidenti e segretario (D12-bis)."""

    request: HttpRequest
    kwargs: dict

    def test_func(self) -> bool:
        assert isinstance(self.request.user, Utente)
        assemblea = Assemblea.objects.filter(pk=self.kwargs["pk"]).first()
        return assemblea is not None and puo_compilare_verbale(self.request.user, assemblea)


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
        return render(request, self.template_name, {"form": AssembleaNuovaForm()})

    def post(self, request):
        form = AssembleaNuovaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        form.instance.creata_da = request.user
        if form.cleaned_data["email_solo_mailpit"] and not mailpit_api.configurato():
            messages.warning(
                request,
                "Mailpit non è configurato sul server: finché non lo è, le email di questa "
                "assemblea di prova non partono.",
            )
        with transaction.atomic():
            assemblea = form.save()
            if form.cleaned_data["elenco_iniziale"] == AssembleaNuovaForm.VUOTA:
                messages.success(
                    request,
                    f"{assemblea} creata con l'elenco vuoto: aggiungi i capi dall'anagrafica.",
                )
                return redirect(reverse("assemblee:aggiungi_anagrafica", args=[assemblea.pk]))
            importati = elenco.importa_elenco(assemblea, request.user)
        messages.success(request, f"{assemblea} creata: {importati} aventi diritto importati.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[assemblea.pk]))


class AssembleaDuplicaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Nuova assemblea con l'elenco, il comitato elettorale e l'ordine del
    giorno di un'altra; niente votazioni (duplica.py)."""

    template_name = "assemblee/assemblea_duplica.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return [*_breadcrumb_assemblee(), {"label": "Duplica assemblea"}]

    def get(self, request, pk):
        origine = get_object_or_404(Assemblea, pk=pk)
        prima = origine.sedute.order_by("convocazione").first()
        iniziali = {
            "titolo": origine.titolo,
            "tipo": origine.tipo,
            "anno_scout": origine.anno_scout,
            "sessione": origine.sessione,
            "sistema_voto": origine.sistema_voto,
            "modalita_voto": origine.modalita_voto,
            "di_prova": origine.di_prova,
            "email_solo_mailpit": origine.email_solo_mailpit,
            "ora_convocazione": prima.ora if prima else None,
            "luogo": prima.luogo if prima else "",
        }
        form = AssembleaCreaForm(initial=iniziali)
        return render(request, self.template_name, {"form": form, "origine": origine})

    def post(self, request, pk):
        origine = get_object_or_404(Assemblea, pk=pk)
        form = AssembleaCreaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "origine": origine})
        form.instance.creata_da = request.user
        with transaction.atomic():
            nuova = form.save()
            copiati = duplica.copia_in(origine, nuova, request.user)
        messages.success(
            request, f"{nuova} creata come copia di {origine}: {copiati} aventi diritto copiati."
        )
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[nuova.pk]))


class EmailProvaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Email di un'assemblea di prova «solo Mailpit», lette da Mailpit (D28)."""

    template_name = "assemblee/email_prova.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Email su Mailpit"})

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk, di_prova=True)
        contesto = {"assemblea": assemblea, "messaggi": None, "errore": False}
        try:
            contesto["messaggi"] = prova.email_su_mailpit(assemblea, request.user)
        except mailpit_api.MailpitNonRaggiungibile:
            contesto["errore"] = True
        return render(request, self.template_name, contesto)

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk, di_prova=True)
        valore = request.POST.get("email_solo_mailpit") == "1"
        try:
            prova.imposta_email_solo_mailpit(assemblea, valore, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            if valore:
                messages.success(request, "Le email di questa assemblea vanno solo su Mailpit.")
                if not mailpit_api.configurato():
                    messages.warning(
                        request,
                        "Mailpit non è configurato sul server: finché non lo è, le email di "
                        "questa assemblea non partono.",
                    )
            else:
                messages.warning(
                    request, "Le email di questa assemblea ora arrivano davvero ai destinatari."
                )
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))


class ElezioniView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Posizioni al voto e candidature preparate in anticipo (candidature.py)."""

    template_name = "assemblee/elezioni.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Elezioni e candidature"})

    def _contesto(self, assemblea, form_posizione=None):
        voci = [
            {
                "posizione": p,
                "candidature": candidature.candidature(p),
                "avvisi": candidature.avvisi(p),
                "votazioni": p.votazioni.count(),
                "form": PosizioneForm(
                    assemblea=assemblea,
                    initial={
                        "incarico": p.incarico,
                        "posti_maschili": p.posti_maschili,
                        "posti_femminili": p.posti_femminili,
                        "posti_indifferenti": p.posti_indifferenti,
                        "punto": p.punto_id,
                    },
                    prefix=f"p{p.pk}",
                ),
            }
            for p in candidature.posizioni(assemblea)
        ]
        return {
            "assemblea": assemblea,
            "voci": voci,
            "modificabile": not assemblea.conclusa,
            "form_posizione": form_posizione or PosizioneForm(assemblea=assemblea),
            "form_candidatura": CandidaturaForm(assemblea=assemblea),
        }

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        return render(request, self.template_name, self._contesto(assemblea))

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        azione = request.POST.get("azione")
        posizione = None
        if request.POST.get("posizione"):
            posizione = get_object_or_404(
                PosizioneVoto, pk=request.POST["posizione"], assemblea=assemblea
            )
        try:
            if azione == "nuova_posizione":
                form = PosizioneForm(request.POST, assemblea=assemblea)
                if not form.is_valid():
                    return render(request, self.template_name, self._contesto(assemblea, form))
                candidature.aggiungi_posizione(assemblea, request.user, **form.cleaned_data)
                messages.success(request, f"Posizione aggiunta: {form.cleaned_data['incarico']}.")
            elif azione == "modifica_posizione" and posizione is not None:
                form = PosizioneForm(request.POST, assemblea=assemblea, prefix=f"p{posizione.pk}")
                if not form.is_valid():
                    raise ValidationError("Controlla incarico e posti.")
                candidature.modifica_posizione(posizione, request.user, **form.cleaned_data)
                messages.success(request, f"Posizione aggiornata: {posizione.incarico}.")
            elif azione == "elimina_posizione" and posizione is not None:
                candidature.elimina_posizione(posizione, request.user)
                messages.success(request, f"Posizione eliminata: {posizione.incarico}.")
            elif azione == "candidatura" and posizione is not None:
                form = CandidaturaForm(request.POST, assemblea=assemblea)
                if not form.is_valid():
                    raise ValidationError("Controlla i dati della candidatura.")
                candidatura = candidature.aggiungi_candidatura(
                    posizione, request.user, **form.cleaned_data
                )
                messages.success(request, f"Candidatura di {candidatura} aggiunta.")
            elif azione == "rimuovi_candidatura":
                candidatura = get_object_or_404(
                    Candidatura, pk=request.POST.get("candidatura"), posizione__assemblea=assemblea
                )
                candidature.rimuovi_candidatura(candidatura, request.user)
                messages.success(request, f"Candidatura di {candidatura} tolta.")
            else:
                raise ValidationError("Operazione non valida.")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        ancora = (
            f"#posizione-{posizione.pk}"
            if posizione is not None and azione != "elimina_posizione"
            else ""
        )
        return redirect(reverse("assemblee:elezioni", args=[pk]) + ancora)


class AssembleaTitoloView(GestisceAssembleeMixin, View):
    """Titolo dell'assemblea: cambia solo il nome mostrato (pagine, PDF,
    email), anche ad assemblea conclusa."""

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        form = TitoloAssembleaForm(request.POST, instance=assemblea)
        if form.is_valid():
            form.save()
            messages.success(request, f"Titolo aggiornato: {assemblea}.")
        else:
            messages.error(request, "Titolo non valido.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))


class AssembleaEliminaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Eliminazione definitiva, solo per le assemblee di prova (prova.py)."""

    template_name = "assemblee/assemblea_elimina.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return [*_breadcrumb_assemblee(), {"label": "Elimina assemblea"}]

    def _assemblea(self, pk) -> Assemblea:
        assemblea = get_object_or_404(Assemblea, pk=pk)
        if not assemblea.di_prova:
            raise PermissionDenied("Solo un'assemblea di prova si può eliminare.")
        return assemblea

    def get(self, request, pk):
        assemblea = self._assemblea(pk)
        contesto = {
            "assemblea": assemblea,
            "aventi": assemblea.aventi_diritto.count(),
            "votazioni": Votazione.objects.filter(seduta__assemblea=assemblea).count(),
        }
        return render(request, self.template_name, contesto)

    def post(self, request, pk):
        assemblea = self._assemblea(pk)
        if request.POST.get("conferma") != "1":
            messages.error(request, "Spunta la conferma per eliminare l'assemblea.")
            return redirect(reverse("assemblee:assemblea_elimina", args=[pk]))
        nome = str(assemblea)
        prova.elimina(assemblea, request.user)
        messages.success(request, f"{nome} eliminata.")
        return redirect(reverse("assemblee:assemblea_lista"))


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
            "seduta_aperta": assemblea.seduta_aperta,
            "operatori": comitato.componenti(assemblea),
            "puo_gestire": puo_gestire,
            "totale_aventi_diritto": elenco.count(),
            "totale_app": elenco.filter(vota_in_app=True).count(),
            "form_operatore": ComitatoAggiungiForm(assemblea=assemblea) if puo_gestire else None,
            "mailpit_configurato": mailpit_api.configurato(),
            "form_titolo": TitoloAssembleaForm(instance=assemblea) if puo_gestire else None,
            "incarichi_per_ruolo": [
                (ruolo, presidenza.incarichi(assemblea, ruolo)) for ruolo in RuoloAssemblea
            ],
            "avvisi_presidenza": presidenza.avvisi(assemblea),
            "ruoli": RuoloAssemblea.choices,
            "puo_compilare": puo_compilare_verbale(request.user, assemblea),
            "sistemi_voto": SistemaVoto.choices,
            "modalita_voto": ModalitaVoto.choices,
            "sistema_modificabile": puo_gestire
            and not assemblea.conclusa
            and not Votazione.objects.filter(seduta__assemblea=assemblea).exists(),
        }
        return render(request, self.template_name, contesto)


MINIMO_CARATTERI_AUTOCOMPLETE = 2
LIMITE_RISULTATI_AUTOCOMPLETE = 15


class ComitatoAutocompleteView(GestisceAssembleeMixin, View):
    """Ricerca fra gli aventi diritto dell'elenco di questa assemblea, per il
    comitato elettorale (esclude chi ne fa già parte) e, con `?per=incarichi`,
    per presidenza, segretario, comitato mozioni e scrutatori. Perimetro
    diverso dalle ricerche soci sull'anagrafica (CLAUDE.md § Ricerca soci):
    qui solo l'elenco, nome, cognome e gruppo, mai recapiti."""

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        query = request.GET.get("q", "").strip()
        if len(query) < MINIMO_CARATTERI_AUTOCOMPLETE:
            return JsonResponse({"risultati": []})
        aventi = assemblea.aventi_diritto.nell_elenco()
        if request.GET.get("per") != "incarichi":
            aventi = aventi.exclude(comitato_elettorale__isnull=False)
        aventi = (
            aventi.filter(
                Q(nome__icontains=query)
                | Q(cognome__icontains=query)
                | Q(codice_socio__icontains=query)
                | Q(gruppo__nome__icontains=query)
            )
            .select_related("gruppo")
            .order_by("cognome", "nome")[:LIMITE_RISULTATI_AUTOCOMPLETE]
        )
        return JsonResponse(
            {
                "risultati": [
                    {"id": a.pk, "nome": a.nome, "cognome": a.cognome, "gruppo": a.gruppo.nome}
                    for a in aventi
                ]
            }
        )


def _messaggio_invito(request, componente, inviato: bool) -> None:
    if inviato:
        messages.success(
            request,
            f"{componente.nome_completo} è nel comitato elettorale: gli è stato inviato "
            f"l'invito per attivare l'account ({componente.utente.email}).",
        )
    else:
        messages.success(request, f"{componente.nome_completo} è nel comitato elettorale.")


class ComitatoAggiungiView(GestisceAssembleeMixin, View):
    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        if assemblea.conclusa:
            raise PermissionDenied("L'assemblea è conclusa.")
        form = ComitatoAggiungiForm(request.POST, assemblea=assemblea)
        if not form.is_valid():
            messages.error(request, "Scegli un capo dall'elenco degli aventi diritto.")
            return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))
        avente = form.cleaned_data["avente"]
        try:
            componente, inviato = comitato.aggiungi(
                assemblea, avente, request.user, accesso=form.cleaned_data["accesso"]
            )
        except comitato.InvitoNonInviato:
            messages.warning(
                request,
                f"{avente.cognome} {avente.nome} è nel comitato elettorale, ma l'email di "
                "invito non è partita: riprova con «Invia invito».",
            )
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            _messaggio_invito(request, componente, inviato)
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))


class ComitatoAccessoView(GestisceAssembleeMixin, View):
    """Account e invito per un componente che non li ha, o nuovo invito per
    chi non ha ancora impostato la password."""

    def post(self, request, pk, operatore_pk):
        componente = get_object_or_404(OperatoreVoto, pk=operatore_pk, assemblea_id=pk)
        try:
            inviato = comitato.dai_accesso(componente, request.user)
        except comitato.InvitoNonInviato:
            messages.warning(request, "L'email di invito non è partita: riprova più tardi.")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            if inviato:
                _messaggio_invito(request, componente, inviato)
            else:
                messages.info(request, f"{componente.nome_completo} ha già un account attivo.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]))


class IncaricoAggiungiView(GestisceAssembleeMixin, View):
    """Presidenti, segretario, comitato mozioni e scrutatori (presidenza.py)."""

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        if assemblea.conclusa:
            raise PermissionDenied("L'assemblea è conclusa.")
        avente = AventeDiritto.objects.filter(
            pk=request.POST.get("avente") or None, assemblea=assemblea
        ).first()
        ruolo = request.POST.get("ruolo", "")
        if avente is None:
            messages.error(request, "Scegli un capo dall'elenco degli aventi diritto.")
            return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]) + "#presidenza")
        try:
            incarico, inviato = presidenza.aggiungi(
                assemblea, ruolo, avente, request.user, accesso=request.POST.get("accesso") == "on"
            )
        except comitato.InvitoNonInviato:
            messages.warning(
                request,
                f"{avente} aggiunto, ma l'email di invito non è partita: riprova con «Invia invito».",
            )
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            testo = f"{avente}: {incarico.get_ruolo_display().lower()}."
            if inviato:
                testo += f" Gli è stato inviato l'invito per attivare l'account ({incarico.utente.email})."
            messages.success(request, testo)
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]) + "#presidenza")


class IncaricoAccessoView(GestisceAssembleeMixin, View):
    def post(self, request, pk, incarico_pk):
        incarico = get_object_or_404(IncaricoAssemblea, pk=incarico_pk, assemblea_id=pk)
        try:
            inviato = presidenza.dai_accesso(incarico, request.user)
        except comitato.InvitoNonInviato:
            messages.warning(request, "L'email di invito non è partita: riprova più tardi.")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            if inviato:
                messages.success(request, f"Invito inviato a {incarico.utente.email}.")
            else:
                messages.info(request, f"{incarico.avente} ha già un account attivo.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]) + "#presidenza")


class IncaricoRimuoviView(GestisceAssembleeMixin, View):
    def post(self, request, pk, incarico_pk):
        incarico = get_object_or_404(IncaricoAssemblea, pk=incarico_pk, assemblea_id=pk)
        try:
            presidenza.rimuovi(incarico, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, f"{incarico.avente}: incarico tolto.")
        return redirect(reverse("assemblee:assemblea_dettaglio", args=[pk]) + "#presidenza")


class ComitatoRimuoviView(GestisceAssembleeMixin, View):
    def post(self, request, pk, operatore_pk):
        componente = get_object_or_404(OperatoreVoto, pk=operatore_pk, assemblea_id=pk)
        try:
            comitato.rimuovi(componente, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(
                request, f"{componente.nome_completo} non fa più parte del comitato elettorale."
            )
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
        solo_incompleti = request.GET.get("incompleti") == "1"
        incompleti = Q(sesso="") | Q(email="")

        righe = tutti if mostra_usciti else nell_elenco
        if solo_incompleti:
            righe = righe.filter(incompleti)
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
            "solo_incompleti": solo_incompleti,
            "totale_senza_sesso": nell_elenco.filter(sesso="").count(),
            "totale_senza_email": nell_elenco.filter(email="").count(),
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
            modifiche = elenco.ripristina(avente, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            dettaglio = ""
            if modifiche:
                campi = ", ".join(m.etichetta.lower() for m in modifiche)
                dettaglio = f" Dati aggiornati dall'anagrafica: {campi}."
            messages.success(request, f"{avente} è di nuovo nell'elenco.{dettaglio}")
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


class AggiungiDaAnagraficaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Capi dall'anagrafica nell'elenco: uno alla volta con la ricerca, un gruppo
    intero, o tutti i censiti (D18-D21)."""

    template_name = "assemblee/aggiungi_anagrafica.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Aggiungi dall'anagrafica"},
        )

    def _assemblea(self, pk) -> Assemblea:
        assemblea = get_object_or_404(Assemblea, pk=pk)
        if assemblea.conclusa:
            raise PermissionDenied("L'assemblea è conclusa.")
        return assemblea

    def get(self, request, pk):
        assemblea = self._assemblea(pk)
        contesto = {
            "assemblea": assemblea,
            "form_gruppo": AggiungiGruppoForm(gruppi=elenco.gruppi_con_censiti(assemblea)),
            "totale": assemblea.aventi_diritto.nell_elenco().count(),
        }
        return render(request, self.template_name, contesto)

    def post(self, request, pk):
        assemblea = self._assemblea(pk)
        azione = request.POST.get("azione")
        try:
            if azione == "capo":
                avente = elenco.aggiungi_da_anagrafica(
                    assemblea, request.POST.get("codice_socio", "").strip(), request.user
                )
                messages.success(request, f"{avente} aggiunto all'elenco.")
            elif azione == "gruppo":
                form = AggiungiGruppoForm(request.POST, gruppi=elenco.gruppi_con_censiti(assemblea))
                if not form.is_valid():
                    raise ValidationError("Scegli un gruppo.")
                gruppo = form.cleaned_data["gruppo"]
                aggiunti = elenco.importa_elenco(assemblea, request.user, gruppi=[gruppo])
                messages.success(request, f"{gruppo}: {aggiunti} capi aggiunti all'elenco.")
            elif azione == "tutti":
                aggiunti = elenco.importa_elenco(assemblea, request.user)
                messages.success(request, f"{aggiunti} capi aggiunti all'elenco.")
            else:
                raise ValidationError("Operazione non valida.")
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        return redirect(reverse("assemblee:aggiungi_anagrafica", args=[pk]))


class AggiungiDaAnagraficaCercaView(GestisceAssembleeMixin, View):
    """Ricerca dei censiti da aggiungere all'elenco: perimetro proprio, distinto
    dalle tre ricerche soci (CLAUDE.md § Ricerca soci). Solo i censiti degli
    anni dell'import non ancora in elenco; nome, cognome, gruppo, mai
    recapiti."""

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        query = request.GET.get("q", "").strip()
        if len(query) < MINIMO_CARATTERI_AUTOCOMPLETE:
            return JsonResponse({"risultati": []})
        censiti = (
            elenco.censiti_aggiungibili(assemblea)
            .filter(
                Q(capo__nome__icontains=query)
                | Q(capo__cognome__icontains=query)
                | Q(capo__codice_socio__icontains=query)
                | Q(gruppo__nome__icontains=query)
            )
            .order_by("capo__cognome", "capo__nome")[:LIMITE_RISULTATI_AUTOCOMPLETE]
        )
        return JsonResponse(
            {
                "risultati": [
                    {
                        "codice_socio": c.capo_id,
                        "nome": c.capo.nome,
                        "cognome": c.capo.cognome,
                        "gruppo": c.gruppo.nome,
                    }
                    for c in censiti
                ]
            }
        )


class RiallineaView(GestisceAssembleeMixin, BreadcrumbExtraMixin, View):
    """Riallineamento dell'elenco con l'anagrafica: anteprima e conferma."""

    template_name = "assemblee/riallinea.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Riallinea con l'anagrafica"},
        )

    def get(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        if assemblea.conclusa:
            raise PermissionDenied("L'assemblea è conclusa.")
        righe = elenco.anteprima_riallinea(assemblea)
        return render(request, self.template_name, {"assemblea": assemblea, "righe": righe})

    def post(self, request, pk):
        assemblea = get_object_or_404(Assemblea, pk=pk)
        try:
            cambiati = elenco.applica_riallinea(assemblea, request.user)
        except ValidationError as errore:
            messages.error(request, " ".join(errore.messages))
        else:
            messages.success(request, f"Riallineamento fatto: {cambiati} capi aggiornati.")
        return redirect(reverse("assemblee:elenco", args=[pk]))


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
            "puo_compilare": puo_compilare_verbale(request.user, assemblea),
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
        # Deleghe degli AE: il delegante conta come presente se il delegato è
        # registrato (art. 4 c.2, stessa regola di quorum.presenti_nell_appello).
        deleghe = {d.delegante_id: d.delegato for d in seduta.deleghe.select_related("delegato")}
        per_delega = {
            delegante: delegato
            for delegante, delegato in deleghe.items()
            if delegato.pk in presenti_ids and delegante not in presenti_ids
        }
        if solo_assenti:
            righe = righe.exclude(pk__in=presenti_ids).exclude(pk__in=per_delega)
        contesto = {
            "assemblea": assemblea,
            "seduta": seduta,
            "appello": appello,
            "deleghe": deleghe,
            "per_delega": per_delega,
            "righe": righe.order_by("cognome", "nome"),
            "presenti_ids": presenti_ids,
            "quorum": stato_quorum(seduta),
            "verifica": verifica,
            "stato_verifica": stato_quorum(seduta, verifica) if verifica else None,
            "precedenti_ids": precedenti_ids,
            "puo_gestire": puo_gestire_assemblee(request.user) and not assemblea.conclusa,
            "solo_precedenti": solo_precedenti,
            "gruppi": Gruppo.objects.filter(
                pk__in=assemblea.aventi_diritto.nell_elenco().values_list("gruppo_id", flat=True)
            ).order_by("nome"),
            "filtro_gruppo": filtro_gruppo,
            "cerca": cerca,
            "solo_assenti": solo_assenti,
            "puo_operare": puo_operare(request.user, assemblea) and seduta.aperta,
            **_stato_codici(seduta),
        }
        return render(request, self.template_name, contesto)


def _stato_codici(seduta: Seduta) -> dict:
    """Chi ha già un codice di voto attivo, e come l'ha avuto (solo voto di Catello)."""
    if not seduta.assemblea.voto_catello:
        return {"codici_email": set(), "codici_banco": set()}
    attivi = codici_voto.aventi_con_codice(seduta)
    return {
        "codici_email": {a for a, c in attivi.items() if c.inviato_per_email},
        "codici_banco": {a for a, c in attivi.items() if not c.inviato_per_email},
    }


class PresenzaView(LoginRequiredMixin, View):
    def post(self, request, pk, seduta_pk, avente_pk):
        seduta = _seduta_visibile(request, pk, seduta_pk)
        avente = get_object_or_404(AventeDiritto, pk=avente_pk, assemblea_id=pk)
        try:
            if request.POST.get("annulla") == "1":
                sedute.annulla_presenza(seduta, avente, request.user)
            else:
                sedute.registra_presenza(seduta, avente, request.user)
                # Voto di Catello: il codice parte subito per email (plan_voto, flusso 1).
                voto_banco.messaggio_invio(
                    request, avente, codici_voto.dopo_la_presenza(seduta, avente, request.user)
                )
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
    """Correzione di email e sesso di un avente, solo per l'assemblea:
    gestori e comitato elettorale al banco."""

    template_name = "assemblee/avente_email.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(
            request,
            {
                "label": "Aventi diritto",
                "url": reverse("assemblee:elenco", args=[request.resolver_match.kwargs["pk"]]),
            },
            {"label": "Dati"},
        )

    def _avente(self, request, pk, avente_pk) -> AventeDiritto:
        assemblea = _assemblea_visibile(request, pk)
        if not puo_operare(request.user, assemblea):
            raise PermissionDenied
        return get_object_or_404(AventeDiritto, pk=avente_pk, assemblea=assemblea)

    def get(self, request, pk, avente_pk):
        avente = self._avente(request, pk, avente_pk)
        form = EmailAventeForm(initial={"email": avente.email, "sesso": avente.sesso})
        return render(request, self.template_name, {"avente": avente, "form": form})

    def post(self, request, pk, avente_pk):
        avente = self._avente(request, pk, avente_pk)
        form = EmailAventeForm(request.POST)
        if form.is_valid():
            try:
                elenco.aggiorna_email(avente, form.cleaned_data["email"], request.user)
                elenco.aggiorna_sesso(avente, form.cleaned_data["sesso"], request.user)
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, f"Dati di {avente} aggiornati.")
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
                    posti=dati["posti"] or 1,
                    candidati=candidati,
                    posizione=dati["posizione"],
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

    @staticmethod
    def _canali_a_mano(votazione) -> list[str]:
        """Con il voto di Catello i voti in app arrivano dall'urna, non dal form."""
        canali_voto = voto.canali(votazione)
        if votazione.seduta.assemblea.voto_catello:
            return [c for c in canali_voto if c != CanaleVoto.APP]
        return canali_voto

    def _contesto(self, request, votazione, form=None):
        canali_voto = self._canali_a_mano(votazione)
        if form is None and not votazione.chiusa:
            form = form_risultati(votazione, canali_voto)
        esito = voto.esito(votazione) if votazione.chiusa else None
        assemblea = votazione.seduta.assemblea
        in_app = assemblea.voto_catello and urna_voto.votazioni_in_app(votazione)
        return {
            "urna": {
                "prevista": in_app,
                "votanti": scrutinio_voto.numero_votanti(votazione) if in_app else 0,
                "da_interpretare": (
                    len(scrutinio_voto.nomi_da_interpretare(votazione)) if in_app else 0
                ),
                "nomi_scritti": len(scrutinio_voto.nomi_scritti(votazione)) if in_app else 0,
                "altra_aperta": (urna_voto.votazione_aperta(votazione.seduta) if in_app else None),
                "nota": scrutinio_voto.nota_verbale(votazione) if in_app else "",
            },
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
        canali_voto = self._canali_a_mano(votazione)
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
                messages.success(
                    request,
                    (
                        "Ballottaggio aperto: apri l'urna elettronica dalla sua pagina."
                        if votazione.seduta.assemblea.voto_catello
                        else "Ballottaggio aperto: si vota solo su carta."
                    ),
                )
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


class OdgView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """Lo modificano i gestori (odg.py); presidenti e segretario lo vedono."""

    template_name = "assemblee/odg.html"

    @classmethod
    def breadcrumb_extra(cls, request):
        return _breadcrumb_assemblea(request, {"label": "Ordine del giorno"})

    def get(self, request, pk):
        assemblea = _assemblea_visibile(request, pk)
        if not puo_vedere_odg(request.user, assemblea):
            raise PermissionDenied
        titoli = set(assemblea.punti_odg.values_list("titolo", flat=True))
        contesto = {
            "puo_gestire": puo_gestire_assemblee(request.user) and not assemblea.conclusa,
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


class PuntoModificaView(AccedeAssembleeMixin, BreadcrumbExtraMixin, View):
    """I gestori cambiano titolo e discussione; presidenti e segretario (e i
    gestori ad assemblea conclusa) scrivono solo la discussione (D12-bis)."""

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

    def _punto(self, request, pk, punto_pk) -> tuple[PuntoOdG, bool]:
        assemblea = _assemblea_visibile(request, pk)
        punto = get_object_or_404(PuntoOdG, pk=punto_pk, assemblea=assemblea)
        if puo_gestire_assemblee(request.user) and not assemblea.conclusa:
            return punto, True
        if puo_compilare_verbale(request.user, assemblea):
            return punto, False
        raise PermissionDenied

    def _render(self, request, punto, form, completo):
        contesto = {
            "punto": punto,
            "assemblea": punto.assemblea,
            "form": form,
            "completo": completo,
        }
        return render(request, self.template_name, contesto)

    def get(self, request, pk, punto_pk):
        punto, completo = self._punto(request, pk, punto_pk)
        if completo:
            form = PuntoOdGForm(initial={"titolo": punto.titolo, "testo": punto.testo})
        else:
            form = DiscussioneForm(initial={"testo": punto.testo})
        return self._render(request, punto, form, completo)

    def post(self, request, pk, punto_pk):
        punto, completo = self._punto(request, pk, punto_pk)
        form = PuntoOdGForm(request.POST) if completo else DiscussioneForm(request.POST)
        if form.is_valid():
            try:
                if completo:
                    odg.modifica_punto(punto, request.user, **form.cleaned_data)
                else:
                    odg.scrivi_discussione(punto, request.user, form.cleaned_data["testo"])
            except ValidationError as errore:
                form.add_error(None, errore)
            else:
                messages.success(request, "Punto salvato.")
                return redirect(reverse("assemblee:odg", args=[pk]))
        return self._render(request, punto, form, completo)


def _nomi_comitato(assemblea: Assemblea) -> list[str]:
    return [c.nome_completo for c in comitato.componenti(assemblea)]


def _suggerimenti_verbale(seduta: Seduta) -> dict:
    """Nomi proposti nei campi del verbale (testo libero comunque ammesso)."""
    elenco_qs = seduta.assemblea.aventi_diritto.nell_elenco().order_by("cognome", "nome")

    def nomi(qs) -> list[str]:
        return [f"{a.cognome} {a.nome}" for a in qs]

    return {
        "nomi_aventi": nomi(elenco_qs),
        "nomi_scrutatori": nomi(elenco_qs.filter(comitato_elettorale__isnull=False)),
        "nomi_rdz": nomi(elenco_qs.filter(rdz=True)),
    }


class VerbaleView(CompilaVerbaleMixin, BreadcrumbExtraMixin, View):
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
            "puo_gestire": puo_gestire_assemblee(self.request.user),
            **_suggerimenti_verbale(seduta),
        }

    def get(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        if seduta.costituita is not True:
            messages.error(request, "Il verbale si redige per una seduta validamente costituita.")
            return redirect(reverse("assemblee:seduta", args=[pk, seduta_pk]))
        form = VerbaleForm(
            instance=verbale_assemblea.verbale_della_seduta(seduta),
            nomi_comitato=_nomi_comitato(seduta.assemblea),
        )
        return render(request, self.template_name, self._contesto(seduta, form))

    def post(self, request, pk, seduta_pk):
        seduta = get_object_or_404(Seduta, pk=seduta_pk, assemblea_id=pk)
        if seduta.costituita is not True:
            raise PermissionDenied
        if request.POST.get("azione") == "riprendi":
            verbale_assemblea.riprendi_dalla_preparazione(seduta, request.user)
            messages.success(request, "Ufficio di presidenza ripreso dalla preparazione.")
            return redirect(reverse("assemblee:verbale", args=[pk, seduta_pk]))
        form = VerbaleForm(
            request.POST,
            instance=verbale_assemblea.verbale_della_seduta(seduta),
            nomi_comitato=_nomi_comitato(seduta.assemblea),
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Dati del verbale salvati.")
            return redirect(reverse("assemblee:verbale", args=[pk, seduta_pk]))
        return render(request, self.template_name, self._contesto(seduta, form))


class VerbalePdfView(CompilaVerbaleMixin, View):
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
