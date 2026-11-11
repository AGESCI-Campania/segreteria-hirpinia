from __future__ import annotations

from typing import cast

from django import forms

from apps.anagrafica.models import BrancaUnita, FunzioneIncarico
from apps.organizzazione.models import Gruppo, anno_scout_corrente

from .models import (
    Assemblea,
    AventeDiritto,
    CanaleVoto,
    Provenienza,
    PuntoOdG,
    Seduta,
    TipoVotazione,
    VariazioneRappresentante,
    VerbaleSeduta,
)


class AssembleaCreaForm(forms.ModelForm):
    """Creazione dell'assemblea insieme alla sua prima convocazione: le
    successive si aggiungono solo se la precedente non ha il quorum (D-70)."""

    data_convocazione = forms.DateField(
        label="Data della prima convocazione", widget=forms.DateInput(attrs={"type": "date"})
    )
    ora_convocazione = forms.TimeField(
        label="Ora", required=False, widget=forms.TimeInput(attrs={"type": "time"})
    )
    luogo = forms.CharField(label="Luogo", max_length=255, required=False)

    class Meta:
        model = Assemblea
        fields = ["tipo", "anno_scout", "sessione", "sistema_voto", "modalita_voto"]
        labels = {"anno_scout": "Anno associativo"}
        help_texts = {
            "sistema_voto": (
                "Per le votazioni a scrutinio segreto. Si può cambiare fino all'apertura della "
                "prima votazione."
            ),
            "modalita_voto": "Solo per il voto in app; si può cambiare anche il giorno stesso.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anno_scout"].initial = anno_scout_corrente()
        # Se non indicati valgono i default del modello (app del Nazionale).
        for nome in ("sistema_voto", "modalita_voto"):
            self.fields[nome].required = False

    def clean(self):
        dati = super().clean()
        for nome in ("sistema_voto", "modalita_voto"):
            if not dati.get(nome):
                dati[nome] = Assemblea._meta.get_field(nome).get_default()
        return dati

    def save(self, commit: bool = True) -> Assemblea:
        assemblea = super().save(commit=commit)
        if commit:
            Seduta.objects.create(
                assemblea=assemblea,
                convocazione=Seduta.Convocazione.PRIMA,
                data=self.cleaned_data["data_convocazione"],
                ora=self.cleaned_data["ora_convocazione"],
                luogo=self.cleaned_data["luogo"],
            )
        return assemblea


class ComitatoAggiungiForm(forms.Form):
    """Nuovo componente del comitato elettorale: un avente diritto scelto con
    l'autocompletamento (il campo nascosto porta l'id)."""

    avente = forms.ModelChoiceField(queryset=AventeDiritto.objects.none(), widget=forms.HiddenInput)
    accesso = forms.BooleanField(
        label="Crea l'account e invia l'invito",
        required=False,
        initial=True,
        help_text=(
            "Serve per registrare presenze, deleghe e risultati. Senza, il capo compare solo "
            "nel verbale."
        ),
    )

    def __init__(self, *args, assemblea: Assemblea, **kwargs):
        super().__init__(*args, **kwargs)
        cast(
            forms.ModelChoiceField, self.fields["avente"]
        ).queryset = assemblea.aventi_diritto.nell_elenco().exclude(
            comitato_elettorale__isnull=False
        )


class AventeInserisciForm(forms.Form):
    """Nuovo capo nell'elenco (D-70): nome, cognome, gruppo e provenienza
    obbligatori; codice socio facoltativo."""

    cognome = forms.CharField(max_length=100)
    nome = forms.CharField(max_length=100)
    gruppo = forms.ModelChoiceField(queryset=Gruppo.objects.none())
    provenienza = forms.ChoiceField(choices=Provenienza.choices, initial=Provenienza.NON_NOTA)
    codice_socio = forms.CharField(
        max_length=20,
        required=False,
        help_text="Facoltativo. Se è fra i censiti già in Catello, il capo vota in app.",
    )
    email = forms.EmailField(
        required=False,
        help_text="Facoltativa. Serve per il tracciato e per ricevere il codice di voto.",
    )

    def __init__(self, *args, assemblea: Assemblea, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["gruppo"]).queryset = Gruppo.objects.attivi(
            assemblea.anno_scout
        ).order_by("nome")
        if assemblea.voto_catello:
            self.fields["codice_socio"].help_text = "Facoltativo: con il voto in app non serve."


class EmailAventeForm(forms.Form):
    email = forms.EmailField(
        required=False,
        help_text="Vale solo per questa assemblea: l'anagrafica non cambia.",
    )


class ImportEmailForm(forms.Form):
    file = forms.FileField(
        label="File Excel del gruppo",
        help_text="Il file scaricato da qui, con la colonna Email verificata dal capogruppo.",
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Il file supera i 2 MB.")
        return file


class IncaricoDichiaratoForm(forms.Form):
    funzione = forms.ChoiceField(
        choices=[("", "—"), *FunzioneIncarico.choices], required=False, label="Funzione"
    )
    branca = forms.ChoiceField(
        choices=[("", "—"), *BrancaUnita.choices], required=False, label="Branca"
    )
    nome_unita = forms.CharField(max_length=100, required=False, label="Unità")


IncaricoDichiaratoFormSet = forms.formset_factory(IncaricoDichiaratoForm, extra=3)


class TrasferisciForm(forms.Form):
    gruppo = forms.ModelChoiceField(queryset=Gruppo.objects.none(), label="Nuovo gruppo")

    def __init__(self, *args, assemblea: Assemblea, attuale: Gruppo, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["gruppo"]).queryset = (
            Gruppo.objects.attivi(assemblea.anno_scout).exclude(pk=attuale.pk).order_by("nome")
        )


class ConvocazioneForm(forms.Form):
    """Seconda o terza convocazione: data, ora e luogo decisi dal Consiglio di Zona."""

    data_convocazione = forms.DateField(
        label="Data", widget=forms.DateInput(attrs={"type": "date"})
    )
    ora_convocazione = forms.TimeField(
        label="Ora", required=False, widget=forms.TimeInput(attrs={"type": "time"})
    )
    luogo = forms.CharField(label="Luogo", max_length=255, required=False)


class _AventeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.cognome} {obj.nome} — {obj.gruppo.nome}"


class _AventiMultipliField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.cognome} {obj.nome} — {obj.gruppo.nome}"


class DelegaForm(forms.Form):
    delegante = _AventeChoiceField(queryset=AventeDiritto.objects.none(), label="AE che delega")
    delegato = _AventeChoiceField(queryset=AventeDiritto.objects.none(), label="Delegato")

    def __init__(self, *args, deleganti: list[AventeDiritto], aventi, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["delegante"]).queryset = (
            AventeDiritto.objects.filter(pk__in=[a.pk for a in deleganti])
            .select_related("gruppo")
            .order_by("cognome", "nome")
        )
        cast(forms.ModelChoiceField, self.fields["delegato"]).queryset = aventi


class QualificheForm(forms.Form):
    ae_zona = forms.BooleanField(label="AE di Zona", required=False)
    rdz = forms.BooleanField(label="Responsabile di Zona", required=False)
    comitato = forms.BooleanField(
        label="Membro del Comitato di Zona",
        required=False,
        help_text="Un Responsabile di Zona è sempre anche membro del Comitato.",
    )


class VotazioneForm(forms.Form):
    tipo = forms.ChoiceField(
        label="Tipo",
        choices=[(v, e) for v, e in TipoVotazione.choices if v != TipoVotazione.BALLOTTAGGIO],
    )
    oggetto = forms.CharField(label="Oggetto", max_length=500)
    punto = forms.ModelChoiceField(
        label="Punto all'ordine del giorno", queryset=PuntoOdG.objects.none(), required=False
    )
    incarico = forms.CharField(
        label="Incarico da eleggere",
        max_length=200,
        required=False,
        help_text="Solo per le elezioni (es. membro del Comitato di Zona).",
    )
    posti = forms.IntegerField(
        label="Posti da eleggere", min_value=1, initial=1, help_text="Solo per le elezioni."
    )
    candidati = _AventiMultipliField(
        label="Candidati dall'elenco",
        queryset=AventeDiritto.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    altri_candidati = forms.CharField(
        label="Altri candidati",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Uno per riga, se non sono nell'elenco degli aventi diritto.",
    )

    def __init__(self, *args, assemblea: Assemblea, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["punto"]).queryset = assemblea.punti_odg.all()
        cast(forms.ModelChoiceField, self.fields["candidati"]).queryset = (
            assemblea.aventi_diritto.nell_elenco()
            .select_related("gruppo")
            .order_by("cognome", "nome")
        )


def form_risultati(votazione, canali_voto: list[str], data=None) -> forms.Form:
    """Form dei risultati costruito sulla votazione: favorevoli/contrari/
    astenuti per canale nelle votazioni sì/no; voti per candidato più schede
    bianche e nulle nelle elezioni."""
    campi: dict[str, forms.Field] = {}
    elezione = votazione.tipo in (TipoVotazione.ELEZIONE, TipoVotazione.BALLOTTAGGIO)
    etichette = dict(CanaleVoto.choices)
    # Prima i voti dei candidati, poi schede bianche e nulle: l'ordine dello spoglio.
    if elezione:
        for candidato in votazione.candidati.all():
            for canale in canali_voto:
                chiave = "voti_app" if canale == CanaleVoto.APP else "voti_carta"
                campi[f"candidato_{candidato.pk}_{chiave}"] = forms.IntegerField(
                    label=f"{candidato.nome} ({etichette[canale].lower()})",
                    min_value=0,
                    initial=0,
                )
    for canale in canali_voto:
        voci = ("bianche", "nulle") if elezione else ("favorevoli", "contrari", "astenuti")
        for voce in voci:
            campi[f"{canale}_{voce}"] = forms.IntegerField(
                label=f"{voce.capitalize()} ({etichette[canale].lower()})", min_value=0, initial=0
            )
    classe = type("RisultatiForm", (forms.Form,), campi)
    return classe(data)


class PuntoOdGForm(forms.Form):
    titolo = forms.CharField(label="Titolo", max_length=500)
    testo = forms.CharField(
        label="Discussione (per il verbale)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="Breve cenno dei fatti e delle questioni proposte (art. 8 del regolamento).",
    )


class VerbaleForm(forms.ModelForm):
    class Meta:
        model = VerbaleSeduta
        fields = [
            "ora_apertura",
            "ora_chiusura",
            "luogo",
            "presidente",
            "segretario",
            "scrutatore_1",
            "scrutatore_2",
            "comitato_mozioni",
            "rdz_1",
            "rdz_2",
            "note_finali",
        ]
        labels = {
            "ora_apertura": "Ora di apertura",
            "ora_chiusura": "Ora di chiusura",
            "scrutatore_1": "Primo scrutatore",
            "scrutatore_2": "Secondo scrutatore",
            "comitato_mozioni": "Comitato mozioni",
        }
        help_texts = {
            "rdz_2": "Lascia vuoto se il posto è vacante.",
        }
        widgets = {
            "ora_apertura": forms.TimeInput(attrs={"type": "time"}),
            "ora_chiusura": forms.TimeInput(attrs={"type": "time"}),
            # Suggerimenti dall'elenco (datalist nel template), testo libero ammesso.
            "presidente": forms.TextInput(attrs={"list": "nomi-aventi"}),
            "segretario": forms.TextInput(attrs={"list": "nomi-aventi"}),
            "scrutatore_1": forms.TextInput(attrs={"list": "nomi-scrutatori"}),
            "scrutatore_2": forms.TextInput(attrs={"list": "nomi-scrutatori"}),
            "rdz_1": forms.TextInput(attrs={"list": "nomi-rdz"}),
            "rdz_2": forms.TextInput(attrs={"list": "nomi-rdz"}),
            "note_finali": forms.Textarea(attrs={"rows": 4}),
        }


class VariazioneRappresentanteForm(forms.ModelForm):
    class Meta:
        model = VariazioneRappresentante
        fields = [
            "ora_apertura",
            "ora_chiusura",
            "cognome",
            "nome",
            "codice_fiscale",
            "comune_nascita",
            "provincia_nascita",
            "data_nascita",
            "indirizzo",
            "civico",
            "cap",
            "comune_residenza",
            "provincia_residenza",
            "varia_sede",
            "sede_indirizzo",
            "sede_civico",
            "sede_cap",
            "sede_comune",
            "sede_provincia",
            "varie",
        ]
        labels = {
            "ora_apertura": "Ora di apertura di questa parte",
            "ora_chiusura": "Ora di chiusura di questa parte",
            "codice_fiscale": "Codice fiscale",
            "comune_nascita": "Comune di nascita",
            "provincia_nascita": "Provincia di nascita",
            "data_nascita": "Data di nascita",
            "comune_residenza": "Comune di residenza",
            "provincia_residenza": "Provincia di residenza",
            "sede_indirizzo": "Indirizzo della nuova sede",
            "sede_civico": "Civico",
            "sede_cap": "CAP",
            "sede_comune": "Comune",
            "sede_provincia": "Provincia",
        }
        widgets = {
            "ora_apertura": forms.TimeInput(attrs={"type": "time"}),
            "ora_chiusura": forms.TimeInput(attrs={"type": "time"}),
            "data_nascita": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "varie": forms.Textarea(attrs={"rows": 3}),
        }
