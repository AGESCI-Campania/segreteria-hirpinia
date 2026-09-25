"""Viste di F6b (sola lettura: elenco, dettaglio, download giustificativi),
F6c (creazione nota/evento/riga documentale), F6d (transizioni FSM da
interfaccia), F6e (vista di verifica con eccezioni per segreteria/RdZ), F6f
(validazione/fusione eventi) e F8 (esportazione, D-68). Il perimetro è
sempre quello di `note_visibili()`/`allegato_visibile()` (D-66) o delle
funzioni di `creazione.py`/`transizioni.py`/`eventi.py`/`esportazione.py`,
mai un controllo di ruolo diretto qui: un capo qualsiasi deve poter
accedere alle proprie note, i permessi di ogni transizione restano
`transizioni.py::_richiedi_permesso_*`. `NotaVerificaListaView`, le viste
sugli eventi e `NotaEsportaView` sono l'eccezione dichiarata: sono
riservate a chi gestisce le note, quindi il controllo di ruolo è nella view
stessa (nessuna funzione di dominio da riusare, non sono un'azione sui dati
di una singola nota)."""

from __future__ import annotations

import csv
import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from openpyxl import Workbook

from apps.accounts.models import Utente
from apps.anagrafica.models import Capo, IncaricoUnita
from apps.core.messaggi import messaggi_per_campo, messaggio_utente

from .allegati import carica_allegato
from .anno_associativo import anno_associativo_per_data
from .creazione import (
    aggiungi_riga_auto,
    aggiungi_riga_documentale,
    crea_nota_bozza,
    duplica_riga_andata_ritorno,
    verifica_nota_modificabile,
)
from .esportazione import genera_esportazione
from .eventi import fondi_eventi, valida_evento
from .forms import (
    EsportazioneNoteForm,
    EventoFondiForm,
    EventoForm,
    ImpostazioniNoteSpeseForm,
    LiquidaNotaForm,
    NotaCreaForm,
    RespingiNotaForm,
    RigaDuplicaForm,
    RigaSpesaAutoForm,
    RigaSpesaDocumentaleForm,
    RilievoNotaForm,
)
from .iban import maschera_iban
from .models import (
    Allegato,
    AutorizzazioneRdzConfig,
    Evento,
    ImpostazioniNoteSpese,
    Localita,
    StatoNota,
)
from .permessi import (
    accede_note_spese,
    e_beneficiario_della_nota,
    e_compilatore_della_nota,
    puo_autorizzare_rdz,
    puo_gestire_note,
    puo_modificare_impostazioni,
)
from .routing import BackendRoutingNonDisponibile
from .transizioni import (
    annulla,
    approva,
    autorizza_rdz,
    conferma_correzione,
    conferma_integrazione,
    invia_nota,
    liquida,
    prendi_in_carico,
    respingi,
    richiedi_conferma,
    richiedi_integrazione,
)
from .verifica import eccezioni_nota, note_in_verifica
from .visibilita import allegato_visibile, note_visibili


class RichiedeGestioneNoteMixin(LoginRequiredMixin, UserPassesTestMixin):
    """F6e/F6f: a differenza delle altre viste del modulo, qui il controllo
    di ruolo sta nella view stessa — non ha un perimetro "capo vs gestione"
    come `note_visibili()`, sono pensate solo per chi gestisce le note."""

    request: HttpRequest

    def test_func(self) -> bool:
        # LoginRequiredMixin garantisce l'autenticazione prima di test_func().
        assert isinstance(self.request.user, Utente)
        return puo_gestire_note(self.request.user)


class RichiedeModificaImpostazioniMixin(LoginRequiredMixin, UserPassesTestMixin):
    """D-35: le impostazioni di sistema del modulo (compreso il report D-64)
    sono modificabili solo da admin e RdZ, non da segreteria — perimetro più
    stretto di `RichiedeGestioneNoteMixin` sopra."""

    request: HttpRequest

    def test_func(self) -> bool:
        assert isinstance(self.request.user, Utente)
        return puo_modificare_impostazioni(self.request.user)


class PanoramicaView(LoginRequiredMixin, View):
    """Landing page del modulo (voce unica "Nota Spese" in "Moduli"): un
    cruscotto con un pulsante per ciascuna funzione a cui l'utente ha
    accesso, stessa condizione di `apps.core.menu.sezioni_menu()` — non va
    duplicata la regola di perimetro, solo il rendering cambia da voci di
    menu a pulsanti."""

    template_name = "note_spese/panoramica.html"

    def get(self, request):
        assert isinstance(request.user, Utente)
        contesto = {
            "accede_note_spese": accede_note_spese(request.user),
            "puo_gestire_note": puo_gestire_note(request.user),
        }
        return render(request, self.template_name, contesto)


class NotaListaView(LoginRequiredMixin, ListView):
    template_name = "note_spese/nota_lista.html"
    context_object_name = "note"

    def get_queryset(self):
        return note_visibili(self.request.user).select_related(
            "beneficiario", "evento", "gruppo_censimento", "centro_costo"
        )


class NotaDettaglioView(LoginRequiredMixin, View):
    template_name = "note_spese/nota_dettaglio.html"

    def get(self, request, pk):
        nota = get_object_or_404(
            note_visibili(request.user).select_related(
                "beneficiario",
                "compilatore",
                "evento",
                "gruppo_censimento",
                "centro_costo",
                "incarico",
                "rilievo_riga",
            ),
            pk=pk,
        )
        righe = nota.righe.select_related(
            "categoria", "localita_partenza", "localita_arrivo"
        ).prefetch_related("allegati", "passeggeri")
        agisce_come_capo = e_beneficiario_della_nota(
            request.user, nota
        ) or e_compilatore_della_nota(request.user, nota)
        puo_modificare = nota.stato == StatoNota.BOZZA and agisce_come_capo
        contesto = {
            "nota": nota,
            "righe": righe,
            "iban_mascherato": maschera_iban(nota.iban),
            "autorizzazioni_rdz": nota.autorizzazioni_rdz.select_related("utente"),
            "puo_gestire_note": puo_gestire_note(request.user),
            "puo_autorizzare_rdz": puo_autorizzare_rdz(request.user),
            "agisce_come_capo": agisce_come_capo,
            "puo_modificare": puo_modificare,
            "richiede_autorizzazione_rdz": (
                ImpostazioniNoteSpese.corrente().autorizzazione_rdz
                != AutorizzazioneRdzConfig.NESSUNA
            ),
        }
        return render(request, self.template_name, contesto)


class AllegatoScaricaView(LoginRequiredMixin, View):
    def get(self, request, pk):
        allegato = get_object_or_404(Allegato, pk=pk)
        if not allegato_visibile(request.user, allegato):
            raise PermissionDenied(
                "Non hai visibilità su nessuna delle note collegate a questo allegato."
            )
        nome_file = allegato.file.name.rsplit("/", 1)[-1]
        return FileResponse(allegato.file.open("rb"), filename=nome_file)


def _applica_errori(form, exc: Exception) -> None:
    campi = messaggi_per_campo(exc) if isinstance(exc, ValidationError) else None
    if campi:
        for campo, testo in campi.items():
            if campo in form.fields:
                form.add_error(campo, testo)
            else:
                form.add_error(None, testo)
    else:
        form.add_error(None, messaggio_utente(exc))


class NotaCreaView(LoginRequiredMixin, View):
    """F6c: creazione della testata in `BOZZA`. Nessuna riga qui — si
    aggiungono dal dettaglio, una volta creata la nota (D-44: le righe
    seguono la testata, non il contrario)."""

    template_name = "note_spese/nota_crea.html"

    def _incarichi_disponibili(self, request):
        if request.user.codice_socio is None:
            return IncaricoUnita.objects.none()
        anno = anno_associativo_per_data(timezone.now().date())
        return IncaricoUnita.objects.filter(
            capo_id=request.user.codice_socio, anno_scout=anno, cessato_il__isnull=True
        )

    def get(self, request):
        form = NotaCreaForm(incarichi_disponibili=self._incarichi_disponibili(request))
        return render(
            request,
            self.template_name,
            {"form": form, "puo_gestire_note": puo_gestire_note(request.user)},
        )

    def post(self, request):
        form = NotaCreaForm(
            request.POST, incarichi_disponibili=self._incarichi_disponibili(request)
        )
        contesto = {"form": form, "puo_gestire_note": puo_gestire_note(request.user)}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        dati = form.cleaned_data
        codice_terzi = dati["beneficiario_codice_socio"].strip()
        try:
            if codice_terzi:
                if not puo_gestire_note(request.user):
                    raise PermissionDenied(
                        "Solo chi gestisce le note può crearne una per un altro capo (D-36)."
                    )
                beneficiario = Capo.objects.filter(pk=codice_terzi).first()
                if beneficiario is None:
                    raise ValidationError(
                        {
                            "beneficiario_codice_socio": f"Nessun capo con codice socio {codice_terzi}."
                        }
                    )
            elif request.user.codice_socio is not None:
                beneficiario = Capo.objects.get(pk=request.user.codice_socio)
            else:
                raise ValidationError(
                    "Il tuo account non è associato a un capo: indica un codice socio beneficiario."
                )

            nota = crea_nota_bozza(
                utente=request.user,
                beneficiario=beneficiario,
                evento=dati["evento"],
                incarico=dati["incarico"],
                incarico_altro=dati["incarico_altro"],
                iban=dati["iban"],
                intestatario_iban=dati["intestatario_iban"],
            )
        except (PermissionDenied, ValidationError) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, "Nota spese creata in bozza.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class EventoCreaView(LoginRequiredMixin, View):
    """D-49: un evento creato da un capo entra subito nell'elenco comune,
    marcato non validato (default già in `Evento.validato`)."""

    template_name = "note_spese/evento_crea.html"

    def get(self, request):
        form = EventoForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = EventoForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        evento = form.save(commit=False)
        evento.creato_da = request.user
        try:
            evento.full_clean()
        except ValidationError as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, {"form": form})
        evento.save()
        messages.success(request, "Evento creato, in attesa di validazione.")
        return redirect(reverse("note_spese:nota_crea"))


class EventoListaView(RichiedeGestioneNoteMixin, ListView):
    """F6f: elenco di tutti gli eventi per chi gestisce le note, con badge
    "non validato" e i comandi di validazione/modifica/fusione (D-49)."""

    template_name = "note_spese/evento_lista.html"
    context_object_name = "eventi"

    def get_queryset(self):
        return Evento.objects.all()


class EventoValidaView(RichiedeGestioneNoteMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(Evento, pk=pk)
        valida_evento(evento, request.user)
        messages.success(request, "Evento validato.")
        return redirect(reverse("note_spese:evento_lista"))


class EventoModificaView(RichiedeGestioneNoteMixin, View):
    """D-49: correzione di un evento (nome/date), non una transizione FSM —
    stesso `EventoForm` già usato in creazione."""

    template_name = "note_spese/evento_modifica.html"

    def get(self, request, pk):
        evento = get_object_or_404(Evento, pk=pk)
        form = EventoForm(instance=evento)
        return render(request, self.template_name, {"form": form, "evento": evento})

    def post(self, request, pk):
        evento = get_object_or_404(Evento, pk=pk)
        form = EventoForm(request.POST, instance=evento)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "evento": evento})
        form.save()
        messages.success(request, "Evento aggiornato.")
        return redirect(reverse("note_spese:evento_lista"))


class EventoFondiView(RichiedeGestioneNoteMixin, View):
    """D-49: fonde `pk` (origine) in un altro evento a scelta — tutte le
    note di origine passano alla destinazione, origine viene eliminato."""

    template_name = "note_spese/evento_fondi.html"

    def get(self, request, pk):
        origine = get_object_or_404(Evento, pk=pk)
        form = EventoFondiForm(origine=origine)
        return render(
            request,
            self.template_name,
            {"form": form, "origine": origine, "n_note": origine.note_spese.count()},
        )

    def post(self, request, pk):
        origine = get_object_or_404(Evento, pk=pk)
        form = EventoFondiForm(request.POST, origine=origine)
        contesto = {"form": form, "origine": origine, "n_note": origine.note_spese.count()}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        try:
            note_spostate = fondi_eventi(origine, form.cleaned_data["destinazione"], request.user)
        except (PermissionDenied, ValidationError) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, f"Eventi fusi: {len(note_spostate)} nota/e spostata/e.")
        return redirect(reverse("note_spese:evento_lista"))


class RigaCreaView(LoginRequiredMixin, View):
    """F6c: solo categorie documentali (D-45) — le categorie chilometriche
    hanno un'interfaccia dedicata, non ancora scritta."""

    template_name = "note_spese/riga_crea.html"

    def get(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        try:
            verifica_nota_modificabile(nota, request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))
        form = RigaSpesaDocumentaleForm()
        return render(request, self.template_name, {"form": form, "nota": nota})

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = RigaSpesaDocumentaleForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "nota": nota})

        try:
            aggiungi_riga_documentale(
                nota=nota,
                utente=request.user,
                categoria=form.cleaned_data["categoria"],
                data=form.cleaned_data["data_spesa"],
                importo=form.cleaned_data["importo"],
                descrizione=form.cleaned_data["descrizione"],
                tratta_testo=form.cleaned_data["tratta_testo"],
            )
        except ValidationError as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, {"form": form, "nota": nota})

        messages.success(request, "Riga aggiunta.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class AllegatoCaricaView(LoginRequiredMixin, View):
    """F6c: carica un giustificativo su una riga già esistente della nota.
    Un solo file per volta, collegato a una sola riga — il caso "documento
    cumulativo su più righe" (D-58) resta un'estensione futura di questa
    stessa vista, non necessaria per il primo giro di compilazione."""

    template_name = "note_spese/allegato_carica.html"

    def _riga(self, request, nota_pk, riga_pk):
        nota = get_object_or_404(note_visibili(request.user), pk=nota_pk)
        riga = get_object_or_404(nota.righe, pk=riga_pk)
        return nota, riga

    def get(self, request, nota_pk, riga_pk):
        nota, riga = self._riga(request, nota_pk, riga_pk)
        try:
            verifica_nota_modificabile(nota, request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))
        return render(request, self.template_name, {"nota": nota, "riga": riga})

    def post(self, request, nota_pk, riga_pk):
        nota, riga = self._riga(request, nota_pk, riga_pk)
        file = request.FILES.get("file")
        contesto = {"nota": nota, "riga": riga}
        if file is None:
            messages.error(request, "Seleziona un file da caricare.")
            return render(request, self.template_name, contesto)
        try:
            verifica_nota_modificabile(nota, request.user)
            carica_allegato(file, [riga], request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return render(request, self.template_name, contesto)

        messages.success(request, "Allegato caricato.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


LIMITE_RISULTATI_LOCALITA = 15
MINIMO_CARATTERI_LOCALITA = 2


class LocalitaRicercaAutocompleteView(LoginRequiredMixin, View):
    """Cerca solo fra le località già in anagrafica (comuni italiani
    precaricati, F1, più le estere già geocodificate, F4): nessuna chiamata
    di rete da qui. La creazione di una nuova località estera al primo uso
    (D-56) resta un passo successivo — vedi `RigaSpesaAutoForm`."""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        if len(query) < MINIMO_CARATTERI_LOCALITA:
            return JsonResponse({"risultati": []})
        localita = Localita.objects.filter(nome__icontains=query).order_by("nome")[
            :LIMITE_RISULTATI_LOCALITA
        ]
        risultati = [
            {"id": loc.pk, "nome": loc.nome, "dettaglio": loc.provincia or loc.stato}
            for loc in localita
        ]
        return JsonResponse({"risultati": risultati})


def _etichette_localita(dati_post) -> dict[str, str]:
    """Ripresenta il form dopo un errore (D-53): i campi di ricerca
    partenza/arrivo sono normali `<input>` non collegati al valore del form
    (solo il campo nascosto lo è), quindi senza questo il testo digitato
    sparirebbe pur restando selezionato l'id giusto — trovato verificando a
    schermo con Andrea."""
    etichette = {}
    for campo in ("localita_partenza", "localita_arrivo"):
        pk = dati_post.get(campo)
        localita = Localita.objects.filter(pk=pk).first() if pk else None
        etichette[campo] = str(localita) if localita else ""
    return etichette


class RigaAutoCreaView(LoginRequiredMixin, View):
    """F6c, continuazione: righe di categoria chilometrica (D-52/D-53)."""

    template_name = "note_spese/riga_auto_crea.html"

    def get(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        try:
            verifica_nota_modificabile(nota, request.user)
        except ValidationError as exc:
            messages.error(request, messaggio_utente(exc))
            return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))
        form = RigaSpesaAutoForm()
        return render(request, self.template_name, {"form": form, "nota": nota})

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = RigaSpesaAutoForm(request.POST)
        contesto = {
            "form": form,
            "nota": nota,
            "etichette_localita": _etichette_localita(request.POST),
        }
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        try:
            aggiungi_riga_auto(
                nota=nota,
                utente=request.user,
                categoria=form.cleaned_data["categoria"],
                data=form.cleaned_data["data_spesa"],
                localita_partenza=form.cleaned_data["localita_partenza"],
                localita_arrivo=form.cleaned_data["localita_arrivo"],
                targa=form.cleaned_data["targa"],
                passeggeri_capi=form.cleaned_data["passeggeri_codici_socio"],
                passeggeri_nomi_liberi=form.cleaned_data["passeggeri_nomi_liberi"],
            )
        except (ValidationError, BackendRoutingNonDisponibile) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, "Riga aggiunta.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class RigaDuplicaView(LoginRequiredMixin, View):
    """D-53: crea il viaggio di ritorno da una riga 'Auto andata e ritorno'
    già inserita."""

    template_name = "note_spese/riga_duplica.html"

    def _riga(self, request, nota_pk, riga_pk):
        nota = get_object_or_404(note_visibili(request.user), pk=nota_pk)
        riga = get_object_or_404(nota.righe, pk=riga_pk)
        return nota, riga

    def get(self, request, nota_pk, riga_pk):
        nota, riga = self._riga(request, nota_pk, riga_pk)
        form = RigaDuplicaForm()
        return render(request, self.template_name, {"form": form, "nota": nota, "riga": riga})

    def post(self, request, nota_pk, riga_pk):
        nota, riga = self._riga(request, nota_pk, riga_pk)
        form = RigaDuplicaForm(request.POST)
        contesto = {"form": form, "nota": nota, "riga": riga}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        try:
            duplica_riga_andata_ritorno(
                riga=riga, utente=request.user, nuova_data=form.cleaned_data["data_spesa"]
            )
        except (ValidationError, BackendRoutingNonDisponibile) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, "Viaggio di ritorno aggiunto.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class _TransizioneSemplicePostView(LoginRequiredMixin, View):
    """F6d: base per le transizioni FSM senza input aggiuntivo (invio,
    presa in carico, conferme, approvazione, autorizzazione RdZ,
    annullamento). Permessi ed effetti collaterali restano interamente in
    `transizioni.py` — qui solo instradamento e messaggio."""

    funzione: staticmethod
    messaggio_successo = ""

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        try:
            type(self).funzione(nota, request.user)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, messaggio_utente(exc))
        else:
            messages.success(request, self.messaggio_successo)
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class NotaInviaView(_TransizioneSemplicePostView):
    funzione = staticmethod(invia_nota)
    messaggio_successo = "Nota inviata."


class NotaPrendiInCaricoView(_TransizioneSemplicePostView):
    funzione = staticmethod(prendi_in_carico)
    messaggio_successo = "Nota presa in carico."


class NotaConfermaIntegrazioneView(_TransizioneSemplicePostView):
    funzione = staticmethod(conferma_integrazione)
    messaggio_successo = "Integrazione confermata."


class NotaConfermaCorrezioneView(_TransizioneSemplicePostView):
    funzione = staticmethod(conferma_correzione)
    messaggio_successo = "Correzione confermata."


class NotaApprovaView(_TransizioneSemplicePostView):
    funzione = staticmethod(approva)
    messaggio_successo = "Nota approvata."


class NotaAutorizzaRdzView(_TransizioneSemplicePostView):
    funzione = staticmethod(autorizza_rdz)
    messaggio_successo = "Autorizzazione RdZ registrata."


class NotaAnnullaView(_TransizioneSemplicePostView):
    funzione = staticmethod(annulla)
    messaggio_successo = "Nota annullata."


class NotaRespingiView(LoginRequiredMixin, View):
    """F6d: causale sempre obbligatoria (D-24), nessun percorso automatico
    che la aggiri."""

    template_name = "note_spese/nota_respingi.html"

    def get(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        return render(request, self.template_name, {"nota": nota, "form": RespingiNotaForm()})

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = RespingiNotaForm(request.POST)
        contesto = {"nota": nota, "form": form}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        try:
            respingi(nota, request.user, form.cleaned_data["causale"])
        except (PermissionDenied, ValidationError) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, "Nota respinta.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class _RilievoView(LoginRequiredMixin, View):
    """F6d: base comune a `richiedi_integrazione` e `richiedi_conferma`
    (D-38) — stessa forma di input (riga + testo), la funzione di
    `transizioni.py` chiamata determina la condizione di sblocco."""

    template_name = "note_spese/nota_rilievo.html"
    funzione: staticmethod
    messaggio_successo = ""
    titolo = ""

    def get(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = RilievoNotaForm(righe=nota.righe.all())
        return render(
            request, self.template_name, {"nota": nota, "form": form, "titolo": self.titolo}
        )

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = RilievoNotaForm(request.POST, righe=nota.righe.all())
        contesto = {"nota": nota, "form": form, "titolo": self.titolo}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        try:
            type(self).funzione(
                nota, request.user, form.cleaned_data["riga"], form.cleaned_data["testo"]
            )
        except (PermissionDenied, ValidationError) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, self.messaggio_successo)
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class NotaRichiediIntegrazioneView(_RilievoView):
    funzione = staticmethod(richiedi_integrazione)
    messaggio_successo = "Richiesta di integrazione inviata."
    titolo = "Richiedi integrazione"


class NotaRichiediConfermaView(_RilievoView):
    funzione = staticmethod(richiedi_conferma)
    messaggio_successo = "Richiesta di conferma inviata."
    titolo = "Richiedi conferma"


class NotaLiquidaView(LoginRequiredMixin, View):
    """F6d: unico punto che valorizza `anno_contabilizzazione` (D-41),
    transizione terminale (D-40)."""

    template_name = "note_spese/nota_liquida.html"

    def get(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = LiquidaNotaForm(
            initial={
                "anno_liquidazione": timezone.now().year,
                "data_pagamento": timezone.now().date(),
            }
        )
        return render(request, self.template_name, {"nota": nota, "form": form})

    def post(self, request, pk):
        nota = get_object_or_404(note_visibili(request.user), pk=pk)
        form = LiquidaNotaForm(request.POST)
        contesto = {"nota": nota, "form": form}
        if not form.is_valid():
            return render(request, self.template_name, contesto)

        try:
            liquida(
                nota,
                request.user,
                anno_liquidazione=form.cleaned_data["anno_liquidazione"],
                modalita_pagamento=form.cleaned_data["modalita_pagamento"],
                data_pagamento=form.cleaned_data["data_pagamento"],
                riferimento_tracciabilita=form.cleaned_data["riferimento_tracciabilita"],
            )
        except (PermissionDenied, ValidationError) as exc:
            _applica_errori(form, exc)
            return render(request, self.template_name, contesto)

        messages.success(request, "Nota liquidata.")
        return redirect(reverse("note_spese:nota_dettaglio", args=[nota.pk]))


class NotaVerificaListaView(RichiedeGestioneNoteMixin, View):
    """F6e: elenco delle note in lavorazione con evidenza delle eccezioni
    (incarico non strutturato D-50, doppioni D-57, capienza indicativa
    D-48). Nessuna di queste blocca l'operatore: sono solo segnalazioni,
    l'approvazione/liquidazione restano possibili anche in loro presenza —
    `verifica.py` è l'unica fonte di queste regole, qui solo instradamento."""

    template_name = "note_spese/nota_verifica_lista.html"

    def get(self, request):
        solo_eccezioni = request.GET.get("solo_eccezioni") == "1"
        righe = [eccezioni_nota(nota) for nota in note_in_verifica(request.user)]
        if solo_eccezioni:
            righe = [riga for riga in righe if riga.ha_eccezioni]
        contesto = {"righe": righe, "solo_eccezioni": solo_eccezioni}
        return render(request, self.template_name, contesto)


class ImpostazioniNoteSpeseView(RichiedeModificaImpostazioniMixin, View):
    """D-35/D-64: unica pagina per l'autorizzazione RdZ e per la
    schedulazione del report ai gestori — nessuna delle due aveva finora
    un'interfaccia dedicata (solo Django admin)."""

    template_name = "note_spese/impostazioni.html"

    def get(self, request):
        form = ImpostazioniNoteSpeseForm(instance=ImpostazioniNoteSpese.corrente())
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ImpostazioniNoteSpeseForm(request.POST, instance=ImpostazioniNoteSpese.corrente())
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        form.save()
        messages.success(request, "Impostazioni aggiornate.")
        return redirect(reverse("note_spese:impostazioni"))


def _esportazione_csv(risultato, nome_file: str) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{nome_file}.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(risultato.intestazioni)
    writer.writerows(risultato.righe)
    return response


def _esportazione_xlsx(risultato, nome_file: str) -> HttpResponse:
    cartella = Workbook()
    foglio = cartella.active
    foglio.append(risultato.intestazioni)
    for riga in risultato.righe:
        foglio.append(riga)
    buffer = io.BytesIO()
    cartella.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{nome_file}.xlsx"'
    return response


class NotaEsportaView(RichiedeGestioneNoteMixin, View):
    """F8/D-68: unico servizio di esportazione, raggruppamento selezionabile
    — `esportazione.py::genera_esportazione()` è l'unica fonte della
    logica, qui solo il form e la scelta fra csv/xlsx."""

    template_name = "note_spese/nota_esporta.html"

    def get(self, request):
        form = EsportazioneNoteForm(initial={"anno_liquidazione": timezone.now().year})
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = EsportazioneNoteForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        dati = form.cleaned_data
        risultato = genera_esportazione(
            request.user,
            anno_liquidazione=dati["anno_liquidazione"],
            raggruppamento=dati["raggruppamento"],
        )
        nome_file = f"note_spese_{dati['raggruppamento'].lower()}_{dati['anno_liquidazione']}"
        if dati["formato"] == "xlsx":
            return _esportazione_xlsx(risultato, nome_file)
        return _esportazione_csv(risultato, nome_file)


class NotaPdfView(LoginRequiredMixin, View):
    """F8/D-67: stesso perimetro di `NotaDettaglioView` (`note_visibili()`,
    D-66) — chi può vedere la nota a schermo può scaricarne il PDF, non solo
    chi gestisce le note. `pdf.py::genera_pdf_nota()` è l'unica fonte del
    contenuto, qui solo instradamento."""

    def get(self, request, pk):
        from .pdf import genera_pdf_nota

        nota = get_object_or_404(
            note_visibili(request.user).select_related(
                "beneficiario", "evento", "gruppo_censimento", "centro_costo", "incarico"
            ),
            pk=pk,
        )
        pdf = genera_pdf_nota(nota)
        response = HttpResponse(pdf, content_type="application/pdf")
        nome_file = nota.numero.replace("/", "-") if nota.numero else f"bozza-{nota.pk}"
        response["Content-Disposition"] = f'inline; filename="nota_spese_{nome_file}.pdf"'
        return response
