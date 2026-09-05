import re

from django import forms
from django.conf import settings

from .models import ImpostazioniPiattaforma, TemplateEmail
from .template_email import VARIABILE_PREFISSO_OGGETTO

_RE_PREFISSO_IN_OGGETTO = re.compile(r"\{\{\s*" + VARIABILE_PREFISSO_OGGETTO + r"\s*\}\}")


class ImpostazioniPiattaformaForm(forms.ModelForm):
    class Meta:
        model = ImpostazioniPiattaforma
        fields = [
            "causale_bonifico_default",
            "prefisso_oggetto_email",
            "firma_html",
            "firma_testo",
            "email_su_mailpit",
        ]
        widgets = {
            "firma_html": forms.Textarea(attrs={"id": "id_firma_html", "rows": 8}),
            "firma_testo": forms.Textarea(attrs={"rows": 5}),
        }

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
            "corpo_testo": forms.Textarea(attrs={"id": "id_corpo_testo", "rows": 10}),
        }

    def clean_oggetto(self):
        oggetto = self.cleaned_data["oggetto"]
        if _RE_PREFISSO_IN_OGGETTO.search(oggetto):
            raise forms.ValidationError(
                f"Il prefisso è già aggiunto automaticamente all'oggetto: non usare "
                f"{{{{ {VARIABILE_PREFISSO_OGGETTO} }}}} qui (puoi usarlo nel corpo o "
                f"nella firma)."
            )
        return oggetto


class CaricaImmagineTemplateEmailForm(forms.Form):
    """`forms.ImageField` (non il campo modello) è ciò che verifica
    davvero il contenuto con Pillow: `Model.full_clean()` da solo non lo fa
    (il controllo vive solo nel form field di Django)."""

    file = forms.ImageField()
