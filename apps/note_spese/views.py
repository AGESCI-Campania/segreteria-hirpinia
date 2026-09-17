"""Viste di sola lettura di F6b: elenco, dettaglio e download dei
giustificativi. Nessuna scrittura qui — creazione/compilazione e transizioni
FSM sono F6c/F6d. Il perimetro è sempre quello di `note_visibili()`/
`allegato_visibile()` (D-66), mai un controllo di ruolo qui: un capo
qualsiasi deve poter accedere, non solo chi ha un ruolo di gestione."""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView

from .iban import maschera_iban
from .models import Allegato
from .permessi import puo_gestire_note
from .visibilita import allegato_visibile, note_visibili


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
        contesto = {
            "nota": nota,
            "righe": righe,
            "iban_mascherato": maschera_iban(nota.iban),
            "autorizzazioni_rdz": nota.autorizzazioni_rdz.select_related("utente"),
            "puo_gestire_note": puo_gestire_note(request.user),
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
