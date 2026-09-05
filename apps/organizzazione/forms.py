from django import forms
from django.core.exceptions import ValidationError

from .iban import valida_iban
from .models import CODICE_ORDINALE_VALIDATOR, Gruppo


class GruppoCreaForm(forms.Form):
    codice = forms.CharField(
        label="Codice ordinale", max_length=8, validators=[CODICE_ORDINALE_VALIDATOR]
    )
    nome = forms.CharField(label="Nome", max_length=100)
    email_istituzionale = forms.EmailField(label="Email istituzionale")


class GruppoModificaForm(forms.ModelForm):
    """`email_istituzionale` non è mai incluso: arriva solo da import (D-35).
    `iban`/`intestazione_conto`: dato bancario sensibile (CLAUDE.md), mai in
    log/messaggi di errore/export generici/viste di elenco — qui solo nel
    form di modifica, tracciato da django-auditlog (`Gruppo` già registrato,
    `apps/organizzazione/apps.py`)."""

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
            "iban",
            "intestazione_conto",
        ]

    def clean_iban(self):
        """Sanifica l'errore: `valida_iban()` include il valore non valido nel
        proprio messaggio (riusato da `chiudi_campagna` che lo scarta a monte,
        vedi apps/contributi/campagne.py) — qui va intercettato per non farlo
        arrivare al template (CLAUDE.md: mai l'IBAN nei messaggi di errore).
        Registrando l'errore già qui, `Model.full_clean()` non rivalida più
        il campo (Django esclude dalla validazione i campi già in errore)."""
        iban = self.cleaned_data.get("iban", "")
        if iban:
            try:
                valida_iban(iban)
            except ValidationError:
                raise forms.ValidationError(
                    "IBAN non valido: verificare formato e codice paese."
                ) from None
        return iban


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
