from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Delega, InvitoAttivazione, Ruolo, SessioneImpersonificazione, Utente


@admin.register(Utente)
class UtenteAdmin(UserAdmin):
    model = Utente
    list_display = ["email", "username", "tipo", "gruppo", "stato", "is_staff"]
    list_filter = ["tipo", "stato", "is_staff", "is_superuser"]
    search_fields = ["email", "username", "codice_socio"]
    fieldsets = (
        *(UserAdmin.fieldsets or ()),
        ("Catello", {"fields": ("tipo", "gruppo", "codice_socio", "stato")}),
    )
    ordering = ["email"]


@admin.register(Ruolo)
class RuoloAdmin(admin.ModelAdmin):
    list_display = ["utente", "tipo", "gruppo", "branca", "settore", "attivo", "data_fine"]
    list_filter = ["tipo", "attivo", "origine"]
    search_fields = ["utente__email"]


@admin.register(Delega)
class DelegaAdmin(admin.ModelAdmin):
    list_display = ["delegante", "delegato", "ruolo", "attiva", "data_fine"]
    list_filter = ["attiva"]
    search_fields = ["delegante__email", "delegato__email"]


@admin.register(InvitoAttivazione)
class InvitoAttivazioneAdmin(admin.ModelAdmin):
    list_display = ["email", "stato", "gruppo", "scadenza", "tentativi", "inviato_il"]
    list_filter = ["stato"]
    search_fields = ["email"]
    readonly_fields = ["codice_hash"]


@admin.register(SessioneImpersonificazione)
class SessioneImpersonificazioneAdmin(admin.ModelAdmin):
    list_display = ["amministratore", "utente_impersonato", "iniziata_il", "terminata_il"]
    readonly_fields = ["amministratore", "utente_impersonato", "iniziata_il", "terminata_il", "ip"]
