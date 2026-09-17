"""Form di F6c: creazione nota, evento, riga documentale. Le regole di
dominio vere e proprie (perimetro D-36, D-45, D-50) restano nel service
layer (`creazione.py`): questi form validano solo forma e presenza dei
campi, mai una seconda copia della logica."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.anagrafica.models import Capo, IncaricoUnita

from .models import CategoriaSpesa, Evento, Localita, TipoCalcolo


class NotaCreaForm(forms.Form):
    beneficiario_codice_socio = forms.CharField(
        required=False,
        label="Codice socio del beneficiario",
        help_text="Lascia vuoto per creare la nota per te stesso. Compilabile solo da chi gestisce le note (D-36).",
    )
    evento = forms.ModelChoiceField(
        queryset=Evento.objects.all().order_by("-data_inizio"), label="Evento"
    )
    incarico = forms.ModelChoiceField(
        queryset=IncaricoUnita.objects.none(), required=False, label="Incarico"
    )
    incarico_altro = forms.CharField(required=False, label="Altro incarico (se non in elenco)")
    iban = forms.CharField(required=False, label="IBAN")
    intestatario_iban = forms.CharField(required=False, label="Intestatario IBAN")

    def __init__(self, *args, incarichi_disponibili=None, **kwargs):
        super().__init__(*args, **kwargs)
        if incarichi_disponibili is not None:
            self.fields["incarico"].queryset = incarichi_disponibili

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("beneficiario_codice_socio"):
            # D-50: per conto terzi l'incarico strutturato eventualmente
            # selezionato appartiene a chi compila, non al beneficiario
            # indicato — non ha senso applicarlo, resta solo il testo libero.
            cleaned["incarico"] = None
        if not cleaned.get("incarico") and not cleaned.get("incarico_altro", "").strip():
            self.add_error(
                "incarico_altro", "Indica un incarico dall'elenco o un testo libero (D-50)."
            )
        return cleaned


class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["nome", "data_inizio", "data_fine"]
        widgets = {
            "data_inizio": forms.DateInput(attrs={"type": "date"}),
            "data_fine": forms.DateInput(attrs={"type": "date"}),
        }


class RigaSpesaDocumentaleForm(forms.Form):
    categoria = forms.ModelChoiceField(
        queryset=CategoriaSpesa.objects.filter(tipo_calcolo=TipoCalcolo.DOCUMENTALE, attivo=True),
        label="Categoria",
    )
    data_spesa = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}))
    descrizione = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    tratta_testo = forms.CharField(required=False, label="Tratta (da/a)")
    importo = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"), label="Importo"
    )


def _lista_valori(grezzo: str) -> list[str]:
    return [pezzo.strip() for pezzo in grezzo.split(",") if pezzo.strip()]


class RigaSpesaAutoForm(forms.Form):
    """D-52/D-53: partenza/arrivo sono `Localita` esistenti, scelte tramite
    l'autocompletamento in `LocalitaRicercaAutocompleteView` (campo
    nascosto, valorizzato via JS) — niente ricerca/creazione di una nuova
    località estera da qui: quel percorso (D-56, geocoding al primo uso)
    resta un passo successivo, non necessario per il primo giro di
    compilazione con le sole città già in anagrafica."""

    categoria = forms.ModelChoiceField(
        queryset=CategoriaSpesa.objects.filter(tipo_calcolo=TipoCalcolo.CHILOMETRICO, attivo=True),
        label="Categoria",
    )
    data_spesa = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}))
    localita_partenza = forms.ModelChoiceField(
        queryset=Localita.objects.all(), widget=forms.HiddenInput, label="Partenza"
    )
    localita_arrivo = forms.ModelChoiceField(
        queryset=Localita.objects.all(), widget=forms.HiddenInput, label="Arrivo"
    )
    targa = forms.CharField(required=False, label="Targa")
    passeggeri_codici_socio = forms.CharField(
        required=False,
        label="Altri passeggeri censiti",
        help_text="Codici socio separati da virgola. Non includere te stesso: il conducente non ha una riga propria (D-52).",
    )
    passeggeri_nomi_liberi = forms.CharField(
        required=False,
        label="Altri passeggeri non censiti",
        help_text="Nomi separati da virgola.",
    )

    def clean_localita_arrivo(self):
        partenza = self.cleaned_data.get("localita_partenza")
        arrivo = self.cleaned_data.get("localita_arrivo")
        if partenza is not None and arrivo is not None and partenza.pk == arrivo.pk:
            raise forms.ValidationError("Partenza e arrivo non possono coincidere.")
        return arrivo

    def clean_passeggeri_codici_socio(self) -> list[Capo]:
        capi = []
        for codice in _lista_valori(self.cleaned_data["passeggeri_codici_socio"]):
            capo = Capo.objects.filter(pk=codice).first()
            if capo is None:
                raise forms.ValidationError(f"Nessun capo con codice socio {codice}.")
            capi.append(capo)
        return capi

    def clean_passeggeri_nomi_liberi(self) -> list[str]:
        return _lista_valori(self.cleaned_data["passeggeri_nomi_liberi"])


class RigaDuplicaForm(forms.Form):
    data_spesa = forms.DateField(
        label="Data del ritorno", widget=forms.DateInput(attrs={"type": "date"})
    )
