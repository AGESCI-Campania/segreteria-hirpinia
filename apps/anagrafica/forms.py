from django import forms


class ImportazioneCSVForm(forms.Form):
    file = forms.FileField(label='CSV "Ricerca Soci" di Buona Caccia')
