"""Form di F6c (creazione nota, evento, riga documentale) e F6d (transizioni
che richiedono un input: respingimento, rilievo, liquidazione). Le regole di
dominio vere e proprie (perimetro D-36, D-45, D-50, permessi delle
transizioni) restano nel service layer (`creazione.py`/`transizioni.py`):
questi form validano solo forma e presenza dei campi, mai una seconda copia
della logica."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.anagrafica.models import Capo, IncaricoUnita

from .models import CategoriaSpesa, Evento, Localita, RigaSpesa, TipoCalcolo


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


class RespingiNotaForm(forms.Form):
    causale = forms.CharField(
        label="Causale del respingimento",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obbligatoria in ogni caso: un respingimento senza causale non è possibile (D-24).",
    )


class RilievoNotaForm(forms.Form):
    """F6d: base comune a `richiedi_integrazione` (D-38, si sblocca solo con
    un nuovo allegato) e `richiedi_conferma` (si sblocca con un semplice
    assenso) — la view sceglie quale funzione di `transizioni.py` chiamare,
    il form valida solo riga e testo."""

    riga = forms.ModelChoiceField(
        queryset=RigaSpesa.objects.none(), label="Riga oggetto del rilievo"
    )
    testo = forms.CharField(label="Motivo del rilievo", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, righe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if righe is not None:
            self.fields["riga"].queryset = righe


class LiquidaNotaForm(forms.Form):
    anno_liquidazione = forms.IntegerField(label="Anno di liquidazione", min_value=2000)
