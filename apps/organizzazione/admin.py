from django.contrib import admin

from .models import AllowlistGruppo, AnnoAssociativo, Gruppo, StatoGruppoAnno


class StatoGruppoAnnoInline(admin.TabularInline):
    model = StatoGruppoAnno
    extra = 0
    readonly_fields = ["disposto_il"]


@admin.register(Gruppo)
class GruppoAdmin(admin.ModelAdmin):
    # IBAN e intestazione conto restano modificabili nel form di dettaglio (serve
    # alla segreteria), ma non compaiono in list_display: mai in una vista di
    # elenco (CLAUDE.md). Ogni modifica è comunque tracciata da auditlog.
    list_display = ["codice", "nome", "is_comitato_zona", "account_consentiti", "origine"]
    search_fields = ["codice", "nome"]
    list_filter = ["is_comitato_zona", "origine"]
    inlines = [StatoGruppoAnnoInline]


@admin.register(StatoGruppoAnno)
class StatoGruppoAnnoAdmin(admin.ModelAdmin):
    list_display = ["gruppo", "anno_scout", "attivo", "disposto_da", "disposto_il"]
    list_filter = ["attivo", "anno_scout"]
    readonly_fields = ["disposto_il"]


@admin.register(AnnoAssociativo)
class AnnoAssociativoAdmin(admin.ModelAdmin):
    list_display = ["anno"]


@admin.register(AllowlistGruppo)
class AllowlistGruppoAdmin(admin.ModelAdmin):
    list_display = ["email", "codice_gruppo", "origine", "creata_il"]
    search_fields = ["email", "codice_gruppo"]
    list_filter = ["origine"]
    readonly_fields = ["creata_il"]
