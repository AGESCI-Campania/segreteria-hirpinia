from django.db import models


class Branca(models.TextChoices):
    """Vocabolario completo della branca *del capo*, derivata dagli incarichi
    (D-08). Non va confuso con `BrancaUnita`, che è la branca dell'unità in
    cui presta servizio (M3)."""

    LC = "LC", "Lupetti/Coccinelle"
    EG = "EG", "Esploratori/Guide"
    RS = "RS", "Rover/Scolte"
    SG = "SG", "Supporto al gruppo"
    AE = "AE", "Assistente ecclesiastico"
    NON_ASSEGNATA = "NON_ASSEGNATA", "Non assegnata"


class BrancaUnita(models.TextChoices):
    """Branca dell'unità di servizio (D-08/§5.3), diversa da `Branca`: qui
    vale per l'unità, non per il capo. Mappata dal valore restituito dal
    parser (`L/C`/`E/G`/`R/S`/`Adulti`/`SCONOSCIUTA`) nel service layer di
    importazione, mai nel parser stesso (D-07)."""

    LC = "LC", "Lupetti/Coccinelle"
    EG = "EG", "Esploratori/Guide"
    RS = "RS", "Rover/Scolte"
    ADULTI = "ADULTI", "Adulti (Comunità Capi)"
    SCONOSCIUTA = "SCONOSCIUTA", "Sconosciuta"


class FunzioneIncarico(models.TextChoices):
    """Vocabolario chiuso delle funzioni (D-08), verificato sul campione reale
    di 218 record. Un valore del PDF che non corrisponde ESATTAMENTE a uno di
    questi non va scritto: finisce nel report anomalie (nessun fuzzy
    matching)."""

    CAPO_UNITA = "CAPO_UNITA", "Capo unità"
    AIUTO_CAPO_UNITA = "AIUTO_CAPO_UNITA", "Aiuto capo unità"
    CAPO_GRUPPO = "CAPO_GRUPPO", "Capo gruppo"
    AE_GRUPPO = "AE_GRUPPO", "Assistente ecclesiastico di gruppo"
    AE_UNITA = "AE_UNITA", "Assistente ecclesiastico di unità"
    SUPPORTO_GRUPPO = "SUPPORTO_GRUPPO", "Servizio di supporto al gruppo"
    SUPPORTO_AZIONE_EDUCATIVA = (
        "SUPPORTO_AZIONE_EDUCATIVA",
        "Servizio di supporto all'azione educativa",
    )
    MAESTRO_NOVIZI = "MAESTRO_NOVIZI", "Maestro dei novizi"


# Sentinella di sola visualizzazione/raggruppamento (D-31): deliberatamente
# non un membro di FunzioneIncarico, così non può mai comparire fra i
# `choices` di IncaricoUnita.funzione. Nessun record con questo valore va mai
# creato: è calcolato, non persistito.
A_DISPOSIZIONE = "A_DISPOSIZIONE"


class OrigineIncarico(models.TextChoices):
    IMPORT = "IMPORT", "Import autorizzazione"
    MANUALE = "MANUALE", "Manuale"


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
    branca = models.CharField(max_length=15, choices=Branca.choices, blank=True, default="")
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


class IncaricoUnita(models.Model):
    """Incarico in unità dichiarato dall'autorizzazione di gruppo (D-08), o
    assegnato a mano (D-32). `gruppo_servizio` è il gruppo la cui
    autorizzazione dichiara l'incarico, mai il gruppo di censimento del capo
    (D-34): un capo può avere incarichi attivi in più gruppi contemporaneamente.
    Non si cancella mai: si cessa (`cessato_il`)."""

    capo = models.ForeignKey(Capo, on_delete=models.CASCADE, related_name="incarichi")
    anno_scout = models.IntegerField()
    gruppo_servizio = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        related_name="incarichi_unita",
        help_text="Gruppo la cui autorizzazione dichiara l'incarico (D-34).",
    )
    codice_unita = models.CharField(max_length=10)
    nome_unita = models.CharField(max_length=100, blank=True)
    branca = models.CharField(max_length=15, choices=BrancaUnita.choices)
    genere_unita = models.CharField(max_length=10, blank=True)
    funzione = models.CharField(max_length=30, choices=FunzioneIncarico.choices)
    livello_foca = models.IntegerField(null=True, blank=True)
    origine = models.CharField(max_length=10, choices=OrigineIncarico.choices)
    cessato_il = models.DateTimeField(
        null=True, blank=True, help_text="Attivo se nullo (D-32). Mai un delete."
    )
    assegnato_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incarichi_assegnati",
        help_text="Valorizzato solo per origine MANUALE.",
    )
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Incarico in unità"
        verbose_name_plural = "Incarichi in unità"
        constraints = [
            models.UniqueConstraint(
                fields=["capo", "anno_scout", "gruppo_servizio", "codice_unita", "funzione"],
                condition=models.Q(cessato_il__isnull=True),
                name="uniq_incarico_unita_attivo",
            )
        ]
        ordering = ["-anno_scout", "capo"]

    def __str__(self) -> str:
        return f"{self.capo_id}: {self.get_funzione_display()} — {self.gruppo_servizio_id} ({self.anno_scout})"


class Pattuglia(models.Model):
    """Pattuglia di Zona per branca (D-08/§5.3), ricalcolata da zero a ogni
    import/assegnazione come i derivati su CensimentoCapo. Solo LC/EG/RS: SG e
    AE non generano pattuglia."""

    BRANCHE_AMMESSE = (Branca.LC, Branca.EG, Branca.RS)

    branca = models.CharField(
        max_length=5, choices=[(b, b.label) for b in (Branca.LC, Branca.EG, Branca.RS)]
    )
    anno_scout = models.IntegerField()

    class Meta:
        verbose_name = "Pattuglia"
        verbose_name_plural = "Pattuglie"
        constraints = [
            models.UniqueConstraint(
                fields=["branca", "anno_scout"], name="uniq_pattuglia_branca_anno"
            )
        ]
        ordering = ["-anno_scout", "branca"]

    def __str__(self) -> str:
        return f"Pattuglia {self.get_branca_display()} {self.anno_scout}"


class MembroPattuglia(models.Model):
    pattuglia = models.ForeignKey(Pattuglia, on_delete=models.CASCADE, related_name="membri")
    capo = models.ForeignKey(Capo, on_delete=models.CASCADE, related_name="pattuglie")

    class Meta:
        verbose_name = "Membro pattuglia"
        verbose_name_plural = "Membri pattuglia"
        constraints = [
            models.UniqueConstraint(fields=["pattuglia", "capo"], name="uniq_membro_pattuglia")
        ]

    def __str__(self) -> str:
        return f"{self.capo_id} — {self.pattuglia}"


class ImportazioneAutorizzazioni(models.Model):
    """Traccia di ogni esecuzione completata dell'import PDF di autorizzazione
    (§6.2, D-09). Nessun campo di stato: il record si crea solo a conferma
    avvenuta, come ImportazioneCSV."""

    anno_scout = models.IntegerField()
    conteggi = models.JSONField(default=dict)
    anomalie = models.JSONField(default=list)
    utente = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importazioni_autorizzazioni",
    )
    eseguita_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Importazione autorizzazioni"
        verbose_name_plural = "Importazioni autorizzazioni"
        ordering = ["-eseguita_il"]

    def __str__(self) -> str:
        return f"Import autorizzazioni {self.anno_scout} del {self.eseguita_il:%d/%m/%Y %H:%M}"


class FileAutorizzazionePDF(models.Model):
    """Un PDF effettivamente applicato in un batch di import (D-09): un PDF
    scartato per snapshot non aggiornato o gruppo non riconosciuto non genera
    questo record, resta solo nelle anomalie del batch."""

    importazione = models.ForeignKey(
        ImportazioneAutorizzazioni, on_delete=models.CASCADE, related_name="file_pdf"
    )
    file = models.FileField(upload_to="import_autorizzazioni/%Y/")
    nome_file_originale = models.CharField(max_length=255, blank=True)
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo", on_delete=models.PROTECT, related_name="file_autorizzazione"
    )
    data_aggiornamento = models.DateField()

    class Meta:
        verbose_name = "File autorizzazione PDF"
        verbose_name_plural = "File autorizzazione PDF"
        ordering = ["-data_aggiornamento"]

    def __str__(self) -> str:
        return f"{self.gruppo_id} ({self.data_aggiornamento:%d/%m/%Y})"


__all__ = [
    "Branca",
    "BrancaUnita",
    "FunzioneIncarico",
    "A_DISPOSIZIONE",
    "OrigineIncarico",
    "OrigineTrasferimento",
    "Capo",
    "CensimentoCapo",
    "TrasferimentoCapo",
    "ImportazioneCSV",
    "IncaricoUnita",
    "Pattuglia",
    "MembroPattuglia",
    "ImportazioneAutorizzazioni",
    "FileAutorizzazionePDF",
]
