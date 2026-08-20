"""Modelli del contributo formazione capi (§5.4, §7). M4 costruisce lo scheletro
FSM (campi di stato, nessuna transizione con effetti di dominio: quelle sono M5,
"la milestone a rischio più alto: concentra FSM, calcolo monetario e permessi",
§9) e i primi due passi del flusso operativo — apertura campagna, inserimento
delle partecipazioni (manuale e xlsx, D-21)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django_fsm import FSMField, FSMModelMixin

from apps.organizzazione.models import AnnoAssociativo


class StatoCampagna(models.TextChoices):
    APERTA = "APERTA", "Aperta"
    IN_VALUTAZIONE = "IN_VALUTAZIONE", "In valutazione"
    CHIUSA = "CHIUSA", "Chiusa"
    LIQUIDATA = "LIQUIDATA", "Liquidata"


class Campagna(FSMModelMixin, models.Model):
    """Campagna annuale del contributo formazione capi (D-10, D-12). `anno` è
    l'anno di chiusura dell'anno associativo (1/10 anno-1 -> 30/9 anno).
    `FSMModelMixin` corregge `refresh_from_db()` per i campi FSM
    `protected=True` (verificato sul sorgente di django-fsm-2: senza questo
    mixin, refresh_from_db() va in crash con lo stesso AttributeError di una
    riassegnazione diretta, perché fa un secondo `setattr` sul campo)."""

    anno = models.IntegerField(unique=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    tetto_per_partecipazione = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("50.00")
    )
    data_inizio_inserimento = models.DateField()
    data_fine_inserimento = models.DateField()
    stato = FSMField(default=StatoCampagna.APERTA, choices=StatoCampagna.choices, protected=True)
    creata_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campagne_create",
    )
    chiusa_il = models.DateTimeField(null=True, blank=True)
    liquidata_il = models.DateTimeField(null=True, blank=True)
    riferimento_bonifico = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Campagna"
        verbose_name_plural = "Campagne"
        ordering = ["-anno"]

    def __str__(self) -> str:
        return f"Campagna {self.anno} ({self.get_stato_display()})"

    def clean(self):
        super().clean()
        if (
            self.data_inizio_inserimento
            and self.data_fine_inserimento
            and self.data_fine_inserimento < self.data_inizio_inserimento
        ):
            raise ValidationError(
                {"data_fine_inserimento": "Non può precedere l'inizio della finestra."}
            )

    @property
    def finestra_associativa(self) -> tuple[datetime.date, datetime.date]:
        """Riusa le property pure di AnnoAssociativo senza richiedere un record
        salvato (D-10: 1/10 anno-1 -> 30/9 anno)."""
        anno_associativo = AnnoAssociativo(anno=self.anno)
        return anno_associativo.data_inizio, anno_associativo.data_fine

    def in_finestra_inserimento(self, alla_data: datetime.date | None = None) -> bool:
        alla_data = alla_data or timezone.localdate()
        return self.data_inizio_inserimento <= alla_data <= self.data_fine_inserimento


class LivelloCampo(models.TextChoices):
    ZONA = "ZONA", "Zona"
    REG = "REG", "Regionale"
    NAZ = "NAZ", "Nazionale"
    ALTRO = "ALTRO", "Altro"


class TipologiaCampo(models.Model):
    """Vocabolario dei tipi di campo (D-11): CFM/CFA/CCG con approvazione
    automatica e quota di default, le altre valutate dal Comitato (M5)."""

    codice = models.CharField(max_length=20, unique=True)
    nome = models.CharField(max_length=150)
    approvazione_automatica = models.BooleanField(default=False)
    quota_default = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    livello = models.CharField(max_length=10, choices=LivelloCampo.choices)
    attiva = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipologia campo"
        verbose_name_plural = "Tipologie campo"
        ordering = ["codice"]

    def __str__(self) -> str:
        return f"{self.codice} — {self.nome}"


class StatoPartecipazione(models.TextChoices):
    INSERITA = "INSERITA", "Inserita"
    APPROVATA = "APPROVATA", "Approvata"
    RESPINTA = "RESPINTA", "Respinta"
    DOCUMENTI_RICHIESTI = "DOCUMENTI_RICHIESTI", "Documenti richiesti"


class Partecipazione(FSMModelMixin, models.Model):
    """Unità di contributo (D-10): un capo che frequenta due campi genera due
    partecipazioni. `gruppo` non è mai un input diretto dell'utente: si risolve
    sempre da CensimentoCapo.gruppo dell'anno della campagna (D-34), ed è
    l'unico campo che la riattribuzione D-29 aggiorna in seguito a un
    trasferimento rilevato dal CSV anagrafico. `FSMModelMixin`: vedi
    commento su Campagna."""

    campagna = models.ForeignKey(Campagna, on_delete=models.PROTECT, related_name="partecipazioni")
    capo = models.ForeignKey(
        "anagrafica.Capo", on_delete=models.PROTECT, related_name="partecipazioni"
    )
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo", on_delete=models.PROTECT, related_name="partecipazioni"
    )
    tipologia = models.ForeignKey(
        TipologiaCampo, on_delete=models.PROTECT, related_name="partecipazioni"
    )
    descrizione_altro = models.CharField(max_length=200, blank=True)
    data_inizio = models.DateField()
    data_fine = models.DateField()
    luogo = models.CharField(max_length=200)
    quota_versata = models.DecimalField(max_digits=10, decimal_places=2)
    stato = FSMField(
        default=StatoPartecipazione.INSERITA, choices=StatoPartecipazione.choices, protected=True
    )
    motivazione_respingimento = models.TextField(blank=True)
    inserita_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partecipazioni_inserite",
    )
    valutata_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partecipazioni_valutate",
    )
    data_valutazione = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Partecipazione"
        verbose_name_plural = "Partecipazioni"
        constraints = [
            models.UniqueConstraint(
                fields=["campagna", "capo", "tipologia", "data_inizio"],
                name="uniq_partecipazione_chiave_logica",
            )
        ]
        ordering = ["-campagna_id", "capo"]

    def __str__(self) -> str:
        return f"{self.capo_id} — {self.tipologia_id} ({self.campagna_id})"

    def clean(self):
        super().clean()
        errors: dict[str, str] = {}
        if (
            self.stato == StatoPartecipazione.RESPINTA
            and not self.motivazione_respingimento.strip()
        ):
            errors["motivazione_respingimento"] = (
                "Un respingimento senza causale non è possibile, in nessun percorso (D-12/D-24)."
            )
        if self.campagna_id and self.data_inizio:
            inizio, fine = self.campagna.finestra_associativa
            if not (inizio <= self.data_inizio <= fine):
                errors["data_inizio"] = (
                    f"Fuori dalla finestra dell'anno associativo {self.campagna.anno} (D-10)."
                )
        if errors:
            raise ValidationError(errors)


class ImportazionePartecipazioni(models.Model):
    """Traccia di ogni esecuzione del caricamento massivo xlsx/CSV (D-21).
    Nessun campo di stato: il record si crea solo a conferma avvenuta, come
    ImportazioneCSV/ImportazioneAutorizzazioni."""

    campagna = models.ForeignKey(
        Campagna, on_delete=models.PROTECT, related_name="importazioni_partecipazioni"
    )
    file = models.FileField(upload_to="import_partecipazioni/%Y/")
    conteggi = models.JSONField(default=dict)
    anomalie = models.JSONField(default=list)
    utente = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importazioni_partecipazioni",
    )
    eseguita_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Importazione partecipazioni"
        verbose_name_plural = "Importazioni partecipazioni"
        ordering = ["-eseguita_il"]

    def __str__(self) -> str:
        return f"Import partecipazioni {self.campagna_id} del {self.eseguita_il:%d/%m/%Y %H:%M}"


__all__ = [
    "StatoCampagna",
    "Campagna",
    "LivelloCampo",
    "TipologiaCampo",
    "StatoPartecipazione",
    "Partecipazione",
    "ImportazionePartecipazioni",
]
