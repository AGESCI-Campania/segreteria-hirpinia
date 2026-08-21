from django.contrib import admin

from .models import (
    Capo,
    CensimentoCapo,
    EsportazioneAnagrafica,
    FileAutorizzazionePDF,
    ImportazioneAutorizzazioni,
    ImportazioneCSV,
    IncaricoUnita,
    MembroPattuglia,
    Pattuglia,
    TrasferimentoCapo,
)


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


class FileAutorizzazionePDFInline(admin.TabularInline):
    model = FileAutorizzazionePDF
    extra = 0
    readonly_fields = ["file", "nome_file_originale", "gruppo", "data_aggiornamento"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportazioneAutorizzazioni)
class ImportazioneAutorizzazioniAdmin(admin.ModelAdmin):
    # È un report, non un modulo di editing.
    list_display = ["eseguita_il", "anno_scout", "utente"]
    list_filter = ["anno_scout"]
    readonly_fields = ["anno_scout", "conteggi", "anomalie", "utente", "eseguita_il"]
    inlines = [FileAutorizzazionePDFInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(IncaricoUnita)
class IncaricoUnitaAdmin(admin.ModelAdmin):
    # Sola lettura, più stringente di TrasferimentoCapo: una modifica diretta
    # bypasserebbe il ricalcolo dei derivati e la sincronizzazione del ruolo CG.
    list_display = [
        "capo",
        "anno_scout",
        "gruppo_servizio",
        "codice_unita",
        "funzione",
        "origine",
        "cessato_il",
    ]
    list_filter = ["anno_scout", "gruppo_servizio", "funzione", "origine"]
    search_fields = ["capo__codice_socio", "capo__cognome", "capo__nome"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pattuglia)
class PattugliaAdmin(admin.ModelAdmin):
    list_display = ["branca", "anno_scout"]
    list_filter = ["anno_scout", "branca"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EsportazioneAnagrafica)
class EsportazioneAnagraficaAdmin(admin.ModelAdmin):
    # Traccia di sola lettura (D-23): mai un modulo di editing.
    list_display = [
        "eseguita_il",
        "anno_scout",
        "utente",
        "profilo_colonne",
        "numero_capi",
        "numero_righe",
    ]
    list_filter = ["anno_scout", "profilo_colonne"]
    readonly_fields = [
        "utente",
        "anno_scout",
        "filtri",
        "profilo_colonne",
        "numero_righe",
        "numero_capi",
        "eseguita_il",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MembroPattuglia)
class MembroPattugliaAdmin(admin.ModelAdmin):
    list_display = ["pattuglia", "capo"]
    list_filter = ["pattuglia__anno_scout", "pattuglia__branca"]
    search_fields = ["capo__codice_socio", "capo__cognome", "capo__nome"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
