from django import forms

from .models import CODICE_ORDINALE_VALIDATOR, Gruppo


class GruppoCreaForm(forms.Form):
    codice = forms.CharField(
        label="Codice ordinale", max_length=8, validators=[CODICE_ORDINALE_VALIDATOR]
    )
    nome = forms.CharField(label="Nome", max_length=100)
    email_istituzionale = forms.EmailField(label="Email istituzionale")


class GruppoModificaForm(forms.ModelForm):
    """`email_istituzionale` non è mai incluso: arriva solo da import (D-35)."""

    class Meta:
        model = Gruppo
        fields = [
            "email_alternativa",
            "indirizzo",
            "civico",
            "cap",
            "comune",
            "provincia",
            "codice_fiscale",
        ]


class GruppoDisattivaForm(forms.Form):
    motivo = forms.CharField(label="Motivazione", widget=forms.Textarea)


class GruppoRiattivaForm(forms.Form):
    anno_scout = forms.IntegerField(label="Anno associativo (anno di chiusura)")
    motivo = forms.CharField(label="Motivazione", widget=forms.Textarea)


class AllowlistCreaForm(forms.Form):
    codice_gruppo = forms.CharField(
        label="Codice gruppo", max_length=8, validators=[CODICE_ORDINALE_VALIDATOR]
    )
    email = forms.EmailField(label="Email")
