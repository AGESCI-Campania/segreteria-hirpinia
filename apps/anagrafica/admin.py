from django.contrib import admin

from .models import Capo, CensimentoCapo, ImportazioneCSV, TrasferimentoCapo


@admin.register(Capo)
class CapoAdmin(admin.ModelAdmin):
    list_display = ["codice_socio", "cognome", "nome", "attivo", "data_disattivazione"]
    search_fields = ["codice_socio", "cognome", "nome"]
    list_filter = ["attivo"]


@admin.register(CensimentoCapo)
class CensimentoCapoAdmin(admin.ModelAdmin):
    list_display = [
        "capo",
        "anno_scout",
        "gruppo",
        "status_socio",
        "livello_foca",
        "a_disposizione",
    ]
    list_filter = ["anno_scout", "gruppo"]
    search_fields = ["capo__codice_socio", "capo__cognome", "capo__nome"]


@admin.register(TrasferimentoCapo)
class TrasferimentoCapoAdmin(admin.ModelAdmin):
    # Registro storico: mai modificabile a mano, solo consultabile.
    list_display = [
        "capo",
        "anno_scout",
        "gruppo_origine",
        "gruppo_destino",
        "rilevato_il",
        "origine",
    ]
    list_filter = ["anno_scout", "origine"]
    search_fields = ["capo__codice_socio", "capo__cognome", "capo__nome"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportazioneCSV)
class ImportazioneCSVAdmin(admin.ModelAdmin):
    # È un report, non un modulo di editing.
    list_display = ["eseguita_il", "anno_scout", "utente"]
    list_filter = ["anno_scout"]
    readonly_fields = ["file", "anno_scout", "conteggi", "anomalie", "utente", "eseguita_il"]
    filter_horizontal = ["capi_disattivati", "capi_riattivati"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
