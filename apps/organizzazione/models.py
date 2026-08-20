from django.core.validators import RegexValidator
from django.db import models

from .iban import valida_iban

CODICE_ORDINALE_VALIDATOR = RegexValidator(
    regex=r"^E\d{4}$",
    message="Il codice ordinale deve avere la forma 'E' seguita da 4 cifre (es. E0133).",
)


class Origine(models.TextChoices):
    IMPORT = "IMPORT", "Import"
    MANUALE = "MANUALE", "Manuale"


class GruppoQuerySet(models.QuerySet):
    def attivi(self, anno: int):
        """Gruppi attivi per `anno`, stessa risoluzione di `Gruppo.e_attivo(anno)`
        ma a livello di queryset, per evitare N+1 query in `gruppi_visibili()`."""
        disattivati = StatoGruppoAnno.objects.filter(
            gruppo=models.OuterRef("pk"),
            anno_scout__lte=anno,
        ).order_by("-anno_scout")
        return self.annotate(
            _ultimo_stato=models.Subquery(disattivati.values("attivo")[:1]),
        ).filter(models.Q(_ultimo_stato=True) | models.Q(_ultimo_stato__isnull=True))


class Gruppo(models.Model):
    """Gruppo scout (Comunità Capi), identificato dall'ordinale AGESCI (D-02)."""

    codice = models.CharField(
        max_length=8,
        primary_key=True,
        validators=[CODICE_ORDINALE_VALIDATOR],
        help_text="Ordinale AGESCI, es. E0133.",
    )
    nome = models.CharField(max_length=100)
    is_comitato_zona = models.BooleanField(
        default=False,
        help_text="True solo per E9001: non è una Comunità Capi (D-33).",
    )
    email_istituzionale = models.EmailField(blank=True)
    indirizzo = models.CharField(max_length=200, blank=True)
    civico = models.CharField(max_length=10, blank=True)
    cap = models.CharField(max_length=10, blank=True)
    comune = models.CharField(max_length=100, blank=True)
    provincia = models.CharField(max_length=5, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    codice_fiscale = models.CharField(max_length=20, blank=True)
    denominazione_sociale = models.CharField(max_length=200, blank=True)
    parrocchia = models.CharField(max_length=200, blank=True)
    diocesi = models.CharField(max_length=100, blank=True)
    iban = models.CharField(max_length=34, blank=True, validators=[valida_iban])
    intestazione_conto = models.CharField(max_length=200, blank=True)
    data_autorizzazione = models.DateField(
        null=True,
        blank=True,
        help_text="Ultima data_aggiornamento importata dall'autorizzazione (D-09, M3).",
    )
    origine = models.CharField(max_length=10, choices=Origine.choices, default=Origine.MANUALE)
    account_consentiti = models.PositiveSmallIntegerField(
        default=1, help_text="E9001 vale 2 (D-33)."
    )

    objects = GruppoQuerySet.as_manager()

    class Meta:
        verbose_name = "Gruppo"
        verbose_name_plural = "Gruppi"
        ordering = ["nome"]

    def __str__(self) -> str:
        return f"{self.nome} ({self.codice})"

    def e_attivo(self, anno: int) -> bool:
        """Risolve lo stato attivo/disattivo per `anno` (D-24): vale il record
        StatoGruppoAnno con anno_scout più alto fra quelli <= anno. In assenza di
        qualunque record il gruppo è considerato attivo di default."""
        ultimo = self.stati_annuali.filter(anno_scout__lte=anno).order_by("-anno_scout").first()
        if ultimo is None:
            return True
        return ultimo.attivo


class StatoGruppoAnno(models.Model):
    """Stato attivo/disattivo di un gruppo per un anno associativo (D-24)."""

    gruppo = models.ForeignKey(Gruppo, on_delete=models.CASCADE, related_name="stati_annuali")
    anno_scout = models.IntegerField()
    attivo = models.BooleanField()
    motivo = models.TextField(blank=True)
    disposto_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stati_gruppo_disposti",
    )
    disposto_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stato gruppo per anno"
        verbose_name_plural = "Stati gruppo per anno"
        constraints = [
            models.UniqueConstraint(fields=["gruppo", "anno_scout"], name="uniq_stato_gruppo_anno")
        ]
        ordering = ["gruppo", "-anno_scout"]

    def __str__(self) -> str:
        stato = "attivo" if self.attivo else "non attivo"
        return f"{self.gruppo_id} — {self.anno_scout}: {stato}"


class AnnoAssociativo(models.Model):
    """Anno associativo scout, identificato dall'anno di chiusura (1/10 - 30/9)."""

    anno = models.IntegerField(unique=True)

    class Meta:
        verbose_name = "Anno associativo"
        verbose_name_plural = "Anni associativi"
        ordering = ["-anno"]

    def __str__(self) -> str:
        return f"{self.anno - 1}/{self.anno}"

    @property
    def data_inizio(self):
        import datetime

        return datetime.date(self.anno - 1, 10, 1)

    @property
    def data_fine(self):
        import datetime

        return datetime.date(self.anno, 9, 30)


def anno_scout_corrente() -> int:
    """Anno di chiusura dell'anno associativo in corso: dal 1° ottobre in poi vale
    l'anno solare successivo (es. 15 novembre 2026 → 2027)."""
    import datetime

    oggi = datetime.date.today()
    return oggi.year + 1 if oggi.month >= 10 else oggi.year


class AllowlistGruppo(models.Model):
    """Coppia (codice_gruppo, email) che abilita la registrazione autonoma di un
    account di gruppo (D-06). In M1/M1b si popola solo a mano (Django admin): la
    derivazione automatica dall'import CSV arriva in M2."""

    codice_gruppo = models.CharField(max_length=8)
    email = models.EmailField()
    origine = models.CharField(max_length=10, choices=Origine.choices, default=Origine.MANUALE)
    creata_il = models.DateTimeField(auto_now_add=True)
    creata_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allowlist_create",
    )

    class Meta:
        verbose_name = "Allowlist gruppo"
        verbose_name_plural = "Allowlist gruppi"
        constraints = [models.UniqueConstraint(fields=["email"], name="uniq_allowlist_email")]
        ordering = ["codice_gruppo", "email"]

    def __str__(self) -> str:
        return f"{self.email} → {self.codice_gruppo}"

    @classmethod
    def risolvi(cls, email: str) -> AllowlistGruppo | None:
        return cls.objects.filter(email__iexact=email).first()
