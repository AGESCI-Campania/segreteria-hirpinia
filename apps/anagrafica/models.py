from django.db import models


class Branca(models.TextChoices):
    """Vocabolario completo, definito ora per evitare un'AlterField in M3: in M2
    resta sempre vuoto, perché è derivato dagli incarichi (D-08), non ancora
    importati."""

    LC = "LC", "Lupetti/Coccinelle"
    EG = "EG", "Esploratori/Guide"
    RS = "RS", "Rover/Scolte"
    SG = "SG", "Supporto al gruppo"
    AE = "AE", "Assistente ecclesiastico"


class OrigineTrasferimento(models.TextChoices):
    IMPORT_CSV = "IMPORT_CSV", "Import CSV anagrafico"
    IMPORT_AUTORIZZAZIONI = "IMPORT_AUTORIZZAZIONI", "Import autorizzazioni"
    MANUALE = "MANUALE", "Manuale"


class Capo(models.Model):
    """Identità persistente della persona (D-22): mai cancellata dall'import,
    solo disattivata. Il gruppo di appartenenza non è un campo qui: esiste solo
    relativamente a un anno, in CensimentoCapo (D-29)."""

    codice_socio = models.CharField(max_length=20, primary_key=True)
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    sesso = models.CharField(max_length=1, blank=True)
    data_nascita = models.DateField(null=True, blank=True)
    comune_nascita = models.CharField(max_length=100, blank=True)
    codice_fiscale = models.CharField(max_length=16, blank=True)
    nazionalita = models.CharField(max_length=100, blank=True)
    indirizzo = models.CharField(max_length=200, blank=True)
    civico = models.CharField(max_length=10, blank=True)
    comune_residenza = models.CharField(max_length=100, blank=True)
    provincia_residenza = models.CharField(max_length=5, blank=True)
    cap = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    cellulare = models.CharField(max_length=30, blank=True)
    professione = models.CharField(max_length=200, blank=True)
    attivo = models.BooleanField(default=True)
    data_disattivazione = models.DateField(
        null=True,
        blank=True,
        help_text="Valorizzata alla disattivazione, azzerata alla riattivazione (D-22).",
    )
    utente = models.OneToOneField(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capo",
        help_text="Account personale collegato. Mai valorizzato dall'import CSV.",
    )

    class Meta:
        verbose_name = "Capo"
        verbose_name_plural = "Capi"
        ordering = ["cognome", "nome"]

    def __str__(self) -> str:
        return f"{self.cognome} {self.nome} ({self.codice_socio})"


class CensimentoCapo(models.Model):
    """Fotografia annuale della persona (D-22): l'ordinale usato per il
    perimetro di D-21 vive qui, non su Capo."""

    capo = models.ForeignKey(Capo, on_delete=models.CASCADE, related_name="censimenti")
    anno_scout = models.IntegerField()
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        related_name="censimenti",
    )
    branca = models.CharField(max_length=5, choices=Branca.choices, blank=True, default="")
    is_capogruppo = models.BooleanField(default=False)
    a_disposizione = models.BooleanField(
        default=True,
        help_text="Derivato: nessun incarico attivo nell'anno (D-31). Ricalcolato "
        "da zero a ogni import.",
    )
    livello_foca = models.IntegerField(null=True, blank=True)
    comunita_socio = models.CharField(max_length=100, blank=True)
    status_socio = models.CharField(max_length=100, blank=True)
    ingresso_coca = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Censimento capo"
        verbose_name_plural = "Censimenti capi"
        constraints = [
            models.UniqueConstraint(fields=["capo", "anno_scout"], name="uniq_censimento_capo_anno")
        ]
        ordering = ["-anno_scout", "capo"]

    def __str__(self) -> str:
        return f"{self.capo_id} — {self.anno_scout} ({self.gruppo_id})"


class TrasferimentoCapo(models.Model):
    """Registro storico dei passaggi fra gruppi (D-29): CensimentoCapo rappresenta
    solo la situazione corrente, questo modello conserva la cronologia."""

    capo = models.ForeignKey(Capo, on_delete=models.CASCADE, related_name="trasferimenti")
    anno_scout = models.IntegerField()
    gruppo_origine = models.ForeignKey(
        "organizzazione.Gruppo", on_delete=models.PROTECT, related_name="trasferimenti_in_uscita"
    )
    gruppo_destino = models.ForeignKey(
        "organizzazione.Gruppo", on_delete=models.PROTECT, related_name="trasferimenti_in_entrata"
    )
    rilevato_il = models.DateTimeField(auto_now_add=True)
    origine = models.CharField(
        max_length=25,
        choices=OrigineTrasferimento.choices,
        default=OrigineTrasferimento.IMPORT_CSV,
    )
    importazione = models.ForeignKey(
        "ImportazioneCSV",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trasferimenti",
    )

    class Meta:
        verbose_name = "Trasferimento capo"
        verbose_name_plural = "Trasferimenti capi"
        ordering = ["-rilevato_il"]

    def __str__(self) -> str:
        return f"{self.capo_id}: {self.gruppo_origine_id} → {self.gruppo_destino_id} ({self.anno_scout})"


class ImportazioneCSV(models.Model):
    """Traccia di ogni esecuzione completata dell'import CSV Buona Caccia. Nessun
    campo di stato: il record si crea solo a conferma avvenuta, dentro la stessa
    transazione che scrive il resto."""

    file = models.FileField(upload_to="import_csv/%Y/")
    anno_scout = models.IntegerField(help_text="Letto dal CSV (colonna ANNO SCOUT), non scelto.")
    conteggi = models.JSONField(default=dict)
    anomalie = models.JSONField(default=list)
    capi_disattivati = models.ManyToManyField(
        Capo, related_name="disattivazioni_import", blank=True
    )
    capi_riattivati = models.ManyToManyField(Capo, related_name="riattivazioni_import", blank=True)
    utente = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importazioni_csv",
    )
    eseguita_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Importazione CSV"
        verbose_name_plural = "Importazioni CSV"
        ordering = ["-eseguita_il"]

    def __str__(self) -> str:
        return f"Import {self.anno_scout} del {self.eseguita_il:%d/%m/%Y %H:%M}"


__all__ = [
    "Branca",
    "OrigineTrasferimento",
    "Capo",
    "CensimentoCapo",
    "TrasferimentoCapo",
    "ImportazioneCSV",
]
