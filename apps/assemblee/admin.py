from django.contrib import admin

from .models import Assemblea, AventeDiritto, IncaricoDichiarato, OperatoreVoto, Seduta


class SedutaInline(admin.TabularInline):
    model = Seduta
    extra = 0


class OperatoreVotoInline(admin.TabularInline):
    model = OperatoreVoto
    extra = 0
    raw_id_fields = ["avente", "utente"]
    readonly_fields = ["nominato_il", "nominato_da"]


@admin.register(Assemblea)
class AssembleaAdmin(admin.ModelAdmin):
    list_display = ["__str__", "sessione", "conclusa_il"]
    list_filter = ["tipo", "anno_scout"]
    readonly_fields = ["creata_il", "creata_da"]
    inlines = [SedutaInline, OperatoreVotoInline]

    def get_readonly_fields(self, request, obj=None):
        # `di_prova` si sceglie solo alla creazione: renderlo vero dopo
        # renderebbe eliminabile un'assemblea vera (apps/assemblee/prova.py).
        campi = list(super().get_readonly_fields(request, obj))
        return [*campi, "di_prova"] if obj is not None else campi


class IncaricoDichiaratoInline(admin.TabularInline):
    model = IncaricoDichiarato
    extra = 0


@admin.register(AventeDiritto)
class AventeDirittoAdmin(admin.ModelAdmin):
    list_display = ["cognome", "nome", "codice_socio", "gruppo", "vota_in_app", "eliminato_il"]
    list_filter = ["assemblea", "origine", "vota_in_app"]
    search_fields = ["cognome", "nome", "codice_socio"]
    # vota_in_app lo calcola solo il service layer (CLAUDE.md § Assemblee).
    readonly_fields = ["vota_in_app", "creato_il", "creato_da", "eliminato_il", "eliminato_da"]
    raw_id_fields = ["capo"]
    inlines = [IncaricoDichiaratoInline]
