from django import forms

from .models import ImpostazioniPiattaforma


class ImpostazioniPiattaformaForm(forms.ModelForm):
    class Meta:
        model = ImpostazioniPiattaforma
        fields = ["causale_bonifico_default"]
