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


class ChoiceFieldMultiploOpzionale(forms.MultipleChoiceField):
    """`MultipleChoiceField` dove il valore vuoto è sempre accettato: una
    select multipla non ha un'opzione "Tutti"/"Tutte" selezionabile fra le
    altre (non avrebbe senso combinarla con scelte reali) — nessuna
    selezione equivale a nessun filtro, non a un errore di validazione."""

    def valid_value(self, value):
        return value == "" or super().valid_value(value)


class SelectMultiploADiscesa(forms.CheckboxSelectMultiple):
    """Checkbox multiple rese come tendina Bootstrap (bottone con etichetta
    riassuntiva + menu a comparsa con scroll), non la `<select multiple>`
    nativa (che mostra un elenco fisso sempre aperto): usa il dropdown di
    Bootstrap 5 già caricato dal tema (`data-bs-auto-close="outside"` per non
    richiuderlo a ogni checkbox), nessuna libreria JS aggiuntiva. I template
    stanno in apps/anagrafica/templates/widgets/ (non nel `templates/`
    di progetto: il renderer di default dei widget Django — `FORM_RENDERER`
    — cerca solo nelle `templates/` delle app via APP_DIRS, non nei `DIRS`
    di `TEMPLATES`). Vedi anche static/{css,js}/multiselect-dropdown.*."""

    template_name = "widgets/select_multiplo_a_discesa.html"
    option_template_name = "widgets/select_multiplo_a_discesa_opzione.html"

    def __init__(self, attrs=None, placeholder=""):
        super().__init__(attrs=attrs)
        self.placeholder = placeholder

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["placeholder"] = self.placeholder
        return context


class EsportazioneAnagraficaForm(forms.Form):
    """Filtri di D-23. `gruppo`/`unita`/`funzione`/`livello_foca` sono select
    multiple (una o più scelte, nessuna scelta = nessun filtro): `gruppo` e
    `unita` diventano select coi valori realmente disponibili quando la view
    passa le scelte (`gruppi_choices`/`unita_choices`/`livello_foca_choices`);
    restano tuple di stringhe in `cleaned_data`, gestite da
    `_filtri_da_dati()` in views.py. Il perimetro (D-23, CG solo il proprio
    gruppo) resta comunque verificato nel service layer
    (`esportazione.genera_righe_esportazione`), non qui — la select è solo
    un aiuto alla compilazione, non il controllo di sicurezza."""

    FORMATO_CHOICES = [("csv", "CSV"), ("xlsx", "XLSX")]

    anno_scout = forms.IntegerField(label="Anno scout")
    gruppo = ChoiceFieldMultiploOpzionale(
        label="Gruppo",
        choices=[],
        required=False,
        widget=SelectMultiploADiscesa(placeholder="Tutti"),
    )
    unita = ChoiceFieldMultiploOpzionale(
        label="Unità",
        choices=[],
        required=False,
        widget=SelectMultiploADiscesa(placeholder="Tutte"),
    )
    branca = ChoiceFieldMultiploOpzionale(
        label="Branca",
        choices=BrancaUnita.choices,
        required=False,
        widget=SelectMultiploADiscesa(placeholder="Tutte"),
    )
    funzione = ChoiceFieldMultiploOpzionale(
        label="Funzione",
        choices=list(FunzioneIncarico.choices) + [(A_DISPOSIZIONE, "A disposizione")],
        required=False,
        widget=SelectMultiploADiscesa(placeholder="Tutte"),
    )
    livello_foca = ChoiceFieldMultiploOpzionale(
        label="Livello Fo.Ca.",
        choices=[],
        required=False,
        widget=SelectMultiploADiscesa(placeholder="Tutti"),
    )
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

    def __init__(
        self,
        *args,
        gruppi_choices=None,
        unita_choices=None,
        livello_foca_choices=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if gruppi_choices is not None:
            self.fields["gruppo"].choices = gruppi_choices
        if unita_choices is not None:
            self.fields["unita"].choices = unita_choices
        if livello_foca_choices is not None:
            self.fields["livello_foca"].choices = livello_foca_choices

    def clean_gruppo(self):
        return tuple(sorted({v.strip().upper() for v in self.cleaned_data["gruppo"] if v}))

    def clean_unita(self):
        return tuple(sorted({v.strip().upper() for v in self.cleaned_data["unita"] if v}))

    def clean_funzione(self):
        return tuple(v for v in self.cleaned_data["funzione"] if v)

    def clean_livello_foca(self):
        valori = {v for v in self.cleaned_data["livello_foca"] if v not in (None, "")}
        return tuple(sorted(int(v) for v in valori))
