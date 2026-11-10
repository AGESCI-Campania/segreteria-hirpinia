from __future__ import annotations

from typing import cast

from django import forms

from apps.accounts.models import StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import BrancaUnita, FunzioneIncarico
from apps.organizzazione.models import Gruppo, anno_scout_corrente

from .models import Assemblea, AventeDiritto, Provenienza, Seduta


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
        fields = ["tipo", "anno_scout", "sessione"]
        labels = {"anno_scout": "Anno associativo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anno_scout"].initial = anno_scout_corrente()

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


class OperatoreAggiungiForm(forms.Form):
    utente = forms.ModelChoiceField(
        label="Utente",
        queryset=Utente.objects.none(),
        help_text="Utente di Catello che registrerà presenze e risultati delle votazioni.",
    )

    def __init__(self, *args, assemblea: Assemblea, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["utente"]).queryset = (
            Utente.objects.filter(tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO)
            .exclude(operatore_assemblee__assemblea=assemblea)
            .order_by("last_name", "first_name", "email")
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

    def __init__(self, *args, assemblea: Assemblea, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ModelChoiceField, self.fields["gruppo"]).queryset = Gruppo.objects.attivi(
            assemblea.anno_scout
        ).order_by("nome")


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
