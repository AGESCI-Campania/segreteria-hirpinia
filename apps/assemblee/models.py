"""Assemblee di Zona (D-70).

L'elenco degli aventi diritto (`AventeDiritto`) è una copia di lavoro propria
di ogni assemblea, mai l'anagrafica: il modulo non scrive `Capo`,
`CensimentoCapo` o `IncaricoUnita`. Un avente diritto può non avere codice
socio (capi da precensire in autunno) e la sua eliminazione dall'elenco non è
un'uscita dall'associazione (D-22)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.anagrafica.models import BrancaUnita, FunzioneIncarico


class TipoAssemblea(models.TextChoices):
    AUTUNNALE = "AUTUNNALE", "Autunnale"
    PRIMAVERILE = "PRIMAVERILE", "Primaverile"


class SessioneAssemblea(models.TextChoices):
    ORDINARIA = "ORDINARIA", "Ordinaria"
    STRAORDINARIA = "STRAORDINARIA", "Straordinaria"


class Assemblea(models.Model):
    tipo = models.CharField(max_length=20, choices=TipoAssemblea.choices)
    anno_scout = models.PositiveIntegerField(
        help_text="Anno associativo in cui si tiene l'assemblea (es. 2027 per il 2026/2027)."
    )
    sessione = models.CharField(
        max_length=20, choices=SessioneAssemblea.choices, default=SessioneAssemblea.ORDINARIA
    )
    conclusa_il = models.DateTimeField(null=True, blank=True)
    creata_il = models.DateTimeField(auto_now_add=True)
    creata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "assemblea"
        verbose_name_plural = "assemblee"
        ordering = ["-anno_scout", "-creata_il"]

    def __str__(self) -> str:
        return (
            f"Assemblea {self.get_tipo_display().lower()} {self.anno_scout - 1}/{self.anno_scout}"
        )

    @property
    def anno_censimento(self) -> int:
        """Anno dei censiti da cui parte l'elenco e contro cui si decide il voto
        in app (D-70): in autunno i censimenti dell'anno in corso non sono
        ancora completi, quindi vale l'anno precedente."""
        if self.tipo == TipoAssemblea.AUTUNNALE:
            return self.anno_scout - 1
        return self.anno_scout

    @property
    def conclusa(self) -> bool:
        return self.conclusa_il is not None


class Seduta(models.Model):
    """Una convocazione dell'assemblea (D-70): la 2ª e la 3ª esistono solo se la
    precedente non ha raggiunto il quorum costitutivo, ciascuna con data, luogo
    e presenze proprie."""

    class Convocazione(models.IntegerChoices):
        PRIMA = 1, "Prima convocazione"
        SECONDA = 2, "Seconda convocazione"
        TERZA = 3, "Terza convocazione"

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="sedute")
    convocazione = models.PositiveSmallIntegerField(choices=Convocazione.choices)
    data = models.DateField()
    ora = models.TimeField(null=True, blank=True)
    luogo = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "seduta"
        verbose_name_plural = "sedute"
        ordering = ["assemblea", "convocazione"]
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "convocazione"], name="seduta_unica_per_convocazione"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_convocazione_display()} del {self.data:%d/%m/%Y}"


class OrigineAvente(models.TextChoices):
    IMPORT = "IMPORT", "Dal censimento"
    MANUALE = "MANUALE", "Inserito a mano"


class Provenienza(models.TextChoices):
    PASSAGGIO_CLAN = "PASSAGGIO_CLAN", "Passaggio dal clan"
    NUOVO_INGRESSO = "NUOVO_INGRESSO", "Nuovo ingresso"
    RIENTRO = "RIENTRO", "Rientro"
    NON_NOTA = "NON_NOTA", "Non nota"


class AventeDirittoQuerySet(models.QuerySet):
    def nell_elenco(self):
        """Aventi diritto non eliminati: gli unici che contano per quorum,
        tracciato e foglio presenze."""
        return self.filter(eliminato_il__isnull=True)


class AventeDiritto(models.Model):
    assemblea = models.ForeignKey(
        Assemblea, on_delete=models.CASCADE, related_name="aventi_diritto"
    )
    # Collegamento all'anagrafica solo in lettura (recapiti per il tracciato,
    # dati del rappresentante legale): null per chi non ha codice socio.
    capo = models.ForeignKey(
        "anagrafica.Capo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    codice_socio = models.CharField(max_length=20, blank=True)
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Gruppo attuale nell'elenco, dopo eventuali trasferimenti.",
    )
    gruppo_origine = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Gruppo del censimento di riferimento: è quello che va nel tracciato.",
    )
    origine = models.CharField(max_length=10, choices=OrigineAvente.choices)
    provenienza = models.CharField(max_length=20, choices=Provenienza.choices, blank=True)
    # Calcolato da un solo punto del service layer (CLAUDE.md § Assemblee),
    # mai impostato a mano da una view.
    vota_in_app = models.BooleanField(default=False)
    eliminato_il = models.DateTimeField(null=True, blank=True)
    eliminato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    creato_il = models.DateTimeField(auto_now_add=True)
    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = AventeDirittoQuerySet.as_manager()

    class Meta:
        verbose_name = "avente diritto"
        verbose_name_plural = "aventi diritto"
        ordering = ["cognome", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "codice_socio"],
                condition=~Q(codice_socio=""),
                name="avente_codice_socio_unico_per_assemblea",
            ),
            # Un capo inserito a mano ha sempre la provenienza (anche "non nota").
            models.CheckConstraint(
                condition=Q(origine=OrigineAvente.IMPORT) | ~Q(provenienza=""),
                name="avente_manuale_con_provenienza",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cognome} {self.nome}"

    @property
    def eliminato(self) -> bool:
        return self.eliminato_il is not None

    @property
    def trasferito(self) -> bool:
        return self.gruppo_origine_id is not None and self.gruppo_origine_id != self.gruppo_id


class IncaricoDichiarato(models.Model):
    """Incarico in unità dichiarato per un capo inserito a mano: facoltativo,
    solo informativo per l'assemblea (non è un `IncaricoUnita`)."""

    avente = models.ForeignKey(AventeDiritto, on_delete=models.CASCADE, related_name="incarichi")
    funzione = models.CharField(max_length=30, choices=FunzioneIncarico.choices)
    branca = models.CharField(max_length=15, choices=BrancaUnita.choices, blank=True)
    nome_unita = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "incarico dichiarato"
        verbose_name_plural = "incarichi dichiarati"

    def __str__(self) -> str:
        return self.get_funzione_display()


class OperatoreVoto(models.Model):
    """Utente incaricato delle operazioni di voto di una sola assemblea (D-70):
    registra presenze, deleghe e risultati, non modifica l'elenco."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="operatori")
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operatore_assemblee"
    )
    nominato_il = models.DateTimeField(auto_now_add=True)
    nominato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "operatore di voto"
        verbose_name_plural = "operatori di voto"
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "utente"], name="operatore_unico_per_assemblea"
            )
        ]

    def __str__(self) -> str:
        return str(self.utente)
