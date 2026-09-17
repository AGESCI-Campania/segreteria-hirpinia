"""Form di F6c: creazione nota, evento, riga documentale. Le regole di
dominio vere e proprie (perimetro D-36, D-45, D-50) restano nel service
layer (`creazione.py`): questi form validano solo forma e presenza dei
campi, mai una seconda copia della logica."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.anagrafica.models import IncaricoUnita

from .models import CategoriaSpesa, Evento, TipoCalcolo


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
