from django.contrib import admin

from .models import ImpostazioniPiattaforma


@admin.register(ImpostazioniPiattaforma)
class ImpostazioniPiattaformaAdmin(admin.ModelAdmin):
    # Singleton (D-A5): si modifica solo l'unica riga esistente.
    list_display = ["causale_bonifico_default"]

    def has_add_permission(self, request):
        return not ImpostazioniPiattaforma.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
