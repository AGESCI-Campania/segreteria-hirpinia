from django import forms

from .models import ImpostazioniPiattaforma, TemplateEmail


class ImpostazioniPiattaformaForm(forms.ModelForm):
    class Meta:
        model = ImpostazioniPiattaforma
        fields = ["causale_bonifico_default"]


class TemplateEmailForm(forms.ModelForm):
    """`codice` non è mai incluso: è la chiave stabile del template,
    assegnata solo alla creazione (dalla data migration di M8), mai
    modificabile da qui."""

    class Meta:
        model = TemplateEmail
        fields = ["oggetto", "corpo_html", "corpo_testo"]
        widgets = {
            "corpo_html": forms.Textarea(attrs={"id": "id_corpo_html", "rows": 15}),
            "corpo_testo": forms.Textarea(attrs={"rows": 10}),
        }
