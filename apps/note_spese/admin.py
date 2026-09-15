from django.contrib import admin

from .models import (
    Allegato,
    AutorizzazioneRdz,
    BudgetCentroCosto,
    CategoriaSpesa,
    CentroCosto,
    Evento,
    ImpostazioniNoteSpese,
    Localita,
    NotaSpese,
    RigaSpesa,
    RigaSpesaPasseggero,
)


def _profondita(nodo) -> int:
    """Depth of a self-referential tree node, used only to indent
    `list_display` in the admin — no mptt/treebeard in the stack (plan
    approved for F1)."""

    profondita = 0
    corrente = nodo.parent
    while corrente is not None:
        profondita += 1
        corrente = corrente.parent
    return profondita


@admin.register(CategoriaSpesa)
class CategoriaSpesaAdmin(admin.ModelAdmin):
    list_display = ["nome_indentato", "tipo_calcolo", "richiede_allegato", "attivo"]
    list_filter = ["tipo_calcolo", "richiede_allegato", "attivo"]
    search_fields = ["nome"]
    autocomplete_fields = ["parent"]

    @admin.display(description="Nome")
    def nome_indentato(self, obj: CategoriaSpesa) -> str:
        return f"{'— ' * _profondita(obj)}{obj.nome}"


class BudgetCentroCostoInline(admin.TabularInline):
    model = BudgetCentroCosto
    extra = 0


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    list_display = ["nome_indentato", "attivo"]
    list_filter = ["attivo"]
    search_fields = ["nome"]
    autocomplete_fields = ["parent"]
    inlines = [BudgetCentroCostoInline]

    @admin.display(description="Nome")
    def nome_indentato(self, obj: CentroCosto) -> str:
        return f"{'— ' * _profondita(obj)}{obj.nome}"


@admin.register(Localita)
class LocalitaAdmin(admin.ModelAdmin):
    list_display = ["nome", "provincia", "stato", "estero", "codice_istat"]
    list_filter = ["estero"]
    search_fields = ["nome", "provincia", "codice_istat"]


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["nome", "data_inizio", "data_fine", "validato"]
    list_filter = ["validato"]
    search_fields = ["nome"]


class RigaSpesaPasseggeroInline(admin.TabularInline):
    model = RigaSpesaPasseggero
    extra = 0
    autocomplete_fields = ["capo"]


class RigaSpesaInline(admin.StackedInline):
    model = RigaSpesa
    extra = 0
    autocomplete_fields = ["categoria", "localita_partenza", "localita_arrivo"]
    # Cache di calcolo (D-45/D-54), non dati da editare qui: la modifica
    # passa dal service layer di F4, non da un salvataggio diretto in admin.
    readonly_fields = ["importo", "distanza_km", "distanza_backend", "distanza_calcolata_il"]


@admin.register(RigaSpesa)
class RigaSpesaAdmin(admin.ModelAdmin):
    # Registrato solo perché AllegatoAdmin.autocomplete_fields lo richiede
    # (admin.E039): l'editing normale di una riga resta dentro NotaSpeseAdmin.
    list_display = ["nota", "categoria", "data", "importo"]
    search_fields = ["nota__numero", "categoria__nome"]
    autocomplete_fields = ["nota", "categoria", "localita_partenza", "localita_arrivo"]


@admin.register(NotaSpese)
class NotaSpeseAdmin(admin.ModelAdmin):
    # `stato` è un FSMField(protected=True): stesso vincolo di CampagnaAdmin
    # in apps/contributi/admin.py, nessuna transizione esposta qui (F3).
    list_display = [
        "numero",
        "beneficiario",
        "evento",
        "stato",
        "anno_spesa",
        "anno_contabilizzazione",
    ]
    list_filter = ["stato", "anno_spesa", "anno_contabilizzazione"]
    search_fields = ["numero", "beneficiario__cognome", "beneficiario__nome"]
    readonly_fields = ["stato", "numero", "anno_spesa", "anno_contabilizzazione", "creata_il"]
    autocomplete_fields = [
        "beneficiario",
        "compilatore",
        "gruppo_censimento",
        "incarico",
        "centro_costo",
    ]
    inlines = [RigaSpesaInline]


@admin.register(Allegato)
class AllegatoAdmin(admin.ModelAdmin):
    list_display = ["file", "caricato_da", "caricato_il"]
    autocomplete_fields = ["righe"]


@admin.register(AutorizzazioneRdz)
class AutorizzazioneRdzAdmin(admin.ModelAdmin):
    # Sola lettura: una firma si crea solo dal service layer
    # (apps/note_spese/transizioni.py::autorizza_rdz), mai a mano da qui.
    list_display = ["nota", "genere", "utente", "creata_il"]
    list_filter = ["genere"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ImpostazioniNoteSpese)
class ImpostazioniNoteSpeseAdmin(admin.ModelAdmin):
    list_display = ["autorizzazione_rdz"]

    def has_add_permission(self, request):
        return not ImpostazioniNoteSpese.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
