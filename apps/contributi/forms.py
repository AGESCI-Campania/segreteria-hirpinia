from django import forms

from .models import Campagna, TipologiaCampo


class CampagnaForm(forms.ModelForm):
    """La scrittura non passa da `form.save()`: la view estrae
    `cleaned_data` e chiama `apps.contributi.campagne.apri_campagna()`, unico
    punto autorizzato a creare una Campagna."""

    class Meta:
        model = Campagna
        fields = [
            "anno",
            "budget",
            "tetto_per_partecipazione",
            "data_inizio_inserimento",
            "data_fine_inserimento",
        ]
        widgets = {
            "data_inizio_inserimento": forms.DateInput(attrs={"type": "date"}),
            "data_fine_inserimento": forms.DateInput(attrs={"type": "date"}),
        }


class PartecipazioneManualeForm(forms.Form):
    codice_socio = forms.CharField(label="Codice socio", max_length=20)
    tipologia = forms.ModelChoiceField(queryset=TipologiaCampo.objects.filter(attiva=True))
    data_inizio = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    data_fine = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    luogo = forms.CharField(max_length=200)
    quota_versata = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Vuota: precompilata dalla quota di default della tipologia.",
    )


class ImportazionePartecipazioniForm(forms.Form):
    file = forms.FileField(label="File xlsx o CSV delle partecipazioni")

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Estensione non ammessa: carica un file .xlsx o .csv.")
        return file
