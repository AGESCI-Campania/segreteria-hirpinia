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
    codice_socio = forms.CharField(max_length=20, widget=forms.HiddenInput)
    tipologia = forms.ModelChoiceField(queryset=TipologiaCampo.objects.filter(attiva=True))
    descrizione_altro = forms.CharField(
        label='Specificare "Altro"',
        max_length=200,
        required=False,
        help_text='Obbligatorio solo se la tipologia scelta è "Altro".',
    )
    data_inizio = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    data_fine = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    luogo = forms.CharField(max_length=200, required=False)
    quota_versata = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=(
            "Precompilata dalla quota di default della tipologia, quando esiste (M17); "
            "resta modificabile."
        ),
    )
    note = forms.CharField(widget=forms.Textarea, required=False)


class ImportazionePartecipazioniForm(forms.Form):
    file = forms.FileField(label="File xlsx o CSV delle partecipazioni")

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Estensione non ammessa: carica un file .xlsx o .csv.")
        return file


class RespingiPartecipazioneForm(forms.Form):
    motivazione = forms.CharField(label="Causale", widget=forms.Textarea, max_length=1000)


class AllegatoPartecipazioneForm(forms.Form):
    file = forms.FileField(label="Documento")
    tipo = forms.CharField(label="Tipo", max_length=100, required=False)


class BonificiGeneraForm(forms.Form):
    FORMATO_CHOICES = [("csv", "CSV"), ("xlsx", "XLSX")]

    causale = forms.CharField(label="Causale", max_length=200)
    formato = forms.ChoiceField(label="Formato", choices=FORMATO_CHOICES, initial="csv")


class LiquidaCampagnaForm(forms.Form):
    data_liquidazione = forms.DateField(
        label="Data del bonifico", widget=forms.DateInput(attrs={"type": "date"})
    )
    riferimento_bonifico = forms.CharField(label="Riferimento", max_length=100)
