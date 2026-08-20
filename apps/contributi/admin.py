from django.contrib import admin

from .models import Campagna, ImportazionePartecipazioni, Partecipazione, TipologiaCampo


@admin.register(Campagna)
class CampagnaAdmin(admin.ModelAdmin):
    # `stato` è un FSMField(protected=True): un ModelAdmin senza readonly su
    # questo campo va in crash al primo salvataggio (ModelForm ri-assegna ogni
    # campo del form anche se invariato). Nessun @transition da esporre in M4.
    list_display = ["anno", "stato", "budget", "tetto_per_partecipazione", "creata_da"]
    list_filter = ["stato"]
    readonly_fields = ["stato"]


@admin.register(TipologiaCampo)
class TipologiaCampoAdmin(admin.ModelAdmin):
    list_display = [
        "codice",
        "nome",
        "livello",
        "approvazione_automatica",
        "quota_default",
        "attiva",
    ]
    list_filter = ["livello", "attiva", "approvazione_automatica"]
    search_fields = ["codice", "nome"]


@admin.register(Partecipazione)
class PartecipazioneAdmin(admin.ModelAdmin):
    list_display = ["capo", "campagna", "gruppo", "tipologia", "stato", "quota_versata"]
    list_filter = ["campagna", "gruppo", "stato", "tipologia"]
    search_fields = ["capo__codice_socio", "capo__cognome", "capo__nome"]
    readonly_fields = ["stato"]


@admin.register(ImportazionePartecipazioni)
class ImportazionePartecipazioniAdmin(admin.ModelAdmin):
    # È un report, non un modulo di editing.
    list_display = ["campagna", "eseguita_il", "utente"]
    list_filter = ["campagna"]
    readonly_fields = ["campagna", "file", "conteggi", "anomalie", "utente", "eseguita_il"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
