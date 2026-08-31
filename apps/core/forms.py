from django import forms
from django.conf import settings

from .models import ImpostazioniPiattaforma, TemplateEmail


class ImpostazioniPiattaformaForm(forms.ModelForm):
    class Meta:
        model = ImpostazioniPiattaforma
        fields = ["causale_bonifico_default", "email_su_mailpit"]

    def clean_email_su_mailpit(self):
        attivo = self.cleaned_data["email_su_mailpit"]
        if attivo and not settings.EMAIL_MAILPIT_HOST:
            raise forms.ValidationError(
                "EMAIL_MAILPIT_HOST non è configurato: impossibile attivare l'invio su Mailpit."
            )
        return attivo


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


class CaricaImmagineTemplateEmailForm(forms.Form):
    """`forms.ImageField` (non il campo modello) è ciò che verifica
    davvero il contenuto con Pillow: `Model.full_clean()` da solo non lo fa
    (il controllo vive solo nel form field di Django)."""

    file = forms.ImageField()
