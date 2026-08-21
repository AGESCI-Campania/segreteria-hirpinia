from django import forms

from .models import (
    A_DISPOSIZIONE,
    BrancaUnita,
    FunzioneIncarico,
    ProfiloColonneEsportazione,
    RaggruppamentoEsportazione,
    StatoFiltroEsportazione,
)


class ImportazioneCSVForm(forms.Form):
    file = forms.FileField(label='CSV "Ricerca Soci" di Buona Caccia')


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Nessun campo nativo Django per l'upload multiplo (verificato: Django
    6.1 non lo offre): pattern documentato ufficialmente su
    `ClearableFileInput.allow_multiple_selected`."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        singolo = super().clean
        data = data if isinstance(data, (list, tuple)) else [data]
        return [singolo(d, initial) for d in data]


class ImportazioneAutorizzazioniForm(forms.Form):
    file = MultipleFileField(
        label="PDF di autorizzazione (uno o più) oppure un file ZIP",
    )

    def clean_file(self):
        file_list = self.cleaned_data["file"]
        for f in file_list:
            if not f.name.lower().endswith((".pdf", ".zip")):
                raise forms.ValidationError(f"Estensione non ammessa: {f.name}")
        return file_list


class RicercaCapoForm(forms.Form):
    codice_socio = forms.CharField(label="Codice socio", max_length=20)


class IncaricoManualeForm(forms.Form):
    codice_socio = forms.CharField(max_length=20, widget=forms.HiddenInput)
    anno_scout = forms.IntegerField(widget=forms.HiddenInput)
    gruppo_servizio = forms.CharField(max_length=8)
    codice_unita = forms.CharField(max_length=10)
    nome_unita = forms.CharField(max_length=100, required=False)
    branca = forms.ChoiceField(choices=BrancaUnita.choices)
    genere_unita = forms.CharField(max_length=10, required=False)
    funzione = forms.ChoiceField(choices=FunzioneIncarico.choices)
    livello_foca = forms.IntegerField(required=False)

    def __init__(self, *args, gruppi_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gruppi_queryset is not None:
            self.fields["gruppo_servizio"] = forms.ModelChoiceField(
                queryset=gruppi_queryset, to_field_name="codice"
            )


class EsportazioneAnagraficaForm(forms.Form):
    """Filtri di D-23. `gruppo`/`unita` sono codici testuali, non
    ModelChoiceField: il perimetro (D-23, CG solo il proprio gruppo) è
    verificato nel service layer (`esportazione.genera_righe_esportazione`),
    non qui — legare la queryset del campo a un anno scelto in form
    complicherebbe senza necessità, dato che il controllo di sicurezza vero
    è comunque lato server."""

    FORMATO_CHOICES = [("csv", "CSV"), ("xlsx", "XLSX")]

    anno_scout = forms.IntegerField(label="Anno scout")
    gruppo = forms.CharField(label="Gruppo (codice)", max_length=8, required=False)
    unita = forms.CharField(label="Unità (codice)", max_length=10, required=False)
    funzione = forms.ChoiceField(
        label="Funzione",
        choices=[("", "Tutte")]
        + list(FunzioneIncarico.choices)
        + [(A_DISPOSIZIONE, "A disposizione")],
        required=False,
    )
    livello_foca = forms.IntegerField(label="Livello FoCa", required=False)
    stato = forms.ChoiceField(
        label="Stato",
        choices=StatoFiltroEsportazione.choices,
        initial=StatoFiltroEsportazione.ATTIVI,
    )
    raggruppamento = forms.ChoiceField(
        label="Raggruppamento",
        choices=RaggruppamentoEsportazione.choices,
        initial=RaggruppamentoEsportazione.NESSUNO,
    )
    profilo_colonne = forms.ChoiceField(
        label="Profilo colonne",
        choices=ProfiloColonneEsportazione.choices,
        initial=ProfiloColonneEsportazione.MINIMO,
    )
    # required=False: nella ricerca (GET, anteprima in tabella) non c'è alcun
    # bottone di esportazione premuto. Il valore arriva sempre dal bottone
    # "Esporta CSV"/"Esporta XLSX" (formmethod="post") nel template, mai da
    # un campo select — vedi EsportazioneAnagraficaView.post().
    formato = forms.ChoiceField(
        label="Formato", choices=FORMATO_CHOICES, initial="csv", required=False
    )

    def clean_gruppo(self):
        return self.cleaned_data["gruppo"].strip().upper()

    def clean_unita(self):
        return self.cleaned_data["unita"].strip().upper()
