from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Ruolo


class AttivazioneForm(forms.Form):
    email = forms.EmailField(widget=forms.HiddenInput)
    codice = forms.CharField(max_length=8, label="Codice ricevuto via email")
    password1 = forms.CharField(widget=forms.PasswordInput, label="Nuova password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Conferma password")

    def clean_codice(self):
        return self.cleaned_data["codice"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Le due password non coincidono.")
        if p1:
            validate_password(p1)
        return cleaned


class RecuperoOtpForm(forms.Form):
    email = forms.EmailField(label="Indirizzo email")


class DelegaForm(forms.Form):
    ruolo = forms.ModelChoiceField(queryset=Ruolo.objects.none())
    email_delegato = forms.EmailField(label="Email della persona da delegare")
    data_fine = forms.DateField(
        label="Scadenza della delega", widget=forms.DateInput(attrs={"type": "date"})
    )
    note = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, ruoli_delegabili=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ruolo"].queryset = ruoli_delegabili or Ruolo.objects.none()


class InvitoSingoloForm(forms.Form):
    email = forms.EmailField(label="Email del destinatario")
    gruppo = forms.CharField(required=False, help_text="Codice ordinale, per un account di gruppo")
    ruolo_proposto = forms.ChoiceField(
        choices=[("", "—")] + list(Ruolo.Tipo.choices), required=False
    )
