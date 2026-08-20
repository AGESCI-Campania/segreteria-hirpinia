import datetime
import secrets
import string

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TipoUtente(models.TextChoices):
    PERSONA = "PERSONA", "Persona"
    GRUPPO = "GRUPPO", "Account funzionale di gruppo"


class StatoUtente(models.TextChoices):
    ATTIVO = "ATTIVO", "Attivo"
    IN_ATTESA = "IN_ATTESA", "In attesa"
    SOSPESO = "SOSPESO", "Sospeso"


class Utente(AbstractUser):
    """Modello utente unico: persona o account funzionale di gruppo (D-03)."""

    email = models.EmailField(unique=True)
    tipo = models.CharField(max_length=10, choices=TipoUtente.choices, default=TipoUtente.PERSONA)
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="account_funzionali",
        help_text="Identifica solo l'account funzionale, mai il perimetro operativo "
        "(D-28/D-33): usare sempre gruppi_visibili().",
    )
    codice_socio = models.CharField(max_length=20, null=True, blank=True, unique=True)
    stato = models.CharField(
        max_length=10, choices=StatoUtente.choices, default=StatoUtente.IN_ATTESA
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "Utente"
        verbose_name_plural = "Utenti"

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.email})"

    def clean(self):
        super().clean()
        if self.tipo == TipoUtente.GRUPPO:
            if not self.gruppo_id:
                raise ValidationError(
                    {"gruppo": "Obbligatorio per un account funzionale di gruppo."}
                )
            if self.codice_socio:
                raise ValidationError({"codice_socio": "Non applicabile a un account di gruppo."})
            consentiti = self.gruppo.account_consentiti
            attuali = (
                Utente.objects.filter(tipo=TipoUtente.GRUPPO, gruppo_id=self.gruppo_id)
                .exclude(pk=self.pk)
                .count()
            )
            if attuali >= consentiti:
                raise ValidationError(
                    {
                        "gruppo": (
                            f"Il gruppo {self.gruppo_id} ha già {attuali} account "
                            f"funzionali su {consentiti} consentiti (D-33)."
                        )
                    }
                )
        elif self.tipo == TipoUtente.PERSONA and self.gruppo_id:
            raise ValidationError({"gruppo": "Un account personale non ha un gruppo funzionale."})


class Ruolo(models.Model):
    """Ruolo effettivo, con scadenza opzionale (D-04). Nessun vincolo di unicità
    su `utente`: un utente può detenere più ruoli (D-28)."""

    class Tipo(models.TextChoices):
        ADMIN = "ADMIN", "Amministratore"
        SEGRETERIA = "SEGRETERIA", "Segreteria"
        RDZ = "RDZ", "Responsabile di Zona"
        AEZ = "AEZ", "Assistente Ecclesiastico di Zona"
        MCZ = "MCZ", "Membro Comitato di Zona"
        CG = "CG", "Capogruppo"
        IABZ = "IABZ", "Incaricato alla Branca di Zona"
        ISZ = "ISZ", "Incaricato ai Settori di Zona"

    class Branca(models.TextChoices):
        LC = "LC", "Lupetti/Coccinelle"
        EG = "EG", "Esploratori/Guide"
        RS = "RS", "Rover/Scolte"

    class Origine(models.TextChoices):
        DERIVATO = "DERIVATO", "Derivato dall'incarico (D-30)"
        AMMINISTRATIVO = "AMMINISTRATIVO", "Amministrativo"

    utente = models.ForeignKey(Utente, on_delete=models.CASCADE, related_name="ruoli")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ruoli_cg",
        help_text="Obbligatorio solo per il ruolo CG.",
    )
    branca = models.CharField(max_length=5, choices=Branca.choices, blank=True)
    settore = models.CharField(max_length=100, blank=True)
    attivo = models.BooleanField(default=True)
    data_inizio = models.DateField(default=timezone.localdate)
    data_fine = models.DateField(null=True, blank=True)
    assegnato_da = models.ForeignKey(
        Utente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ruoli_assegnati",
    )
    origine = models.CharField(
        max_length=15, choices=Origine.choices, default=Origine.AMMINISTRATIVO
    )

    class Meta:
        verbose_name = "Ruolo"
        verbose_name_plural = "Ruoli"
        ordering = ["utente", "tipo"]

    def __str__(self) -> str:
        etichetta = self.get_tipo_display()
        if self.gruppo_id:
            etichetta += f" - {self.gruppo_id}"
        if self.branca:
            etichetta += f" ({self.get_branca_display()})"
        return f"{etichetta} — {self.utente}"

    @property
    def is_scaduto(self) -> bool:
        return self.data_fine is not None and self.data_fine < timezone.localdate()

    def clean(self):
        super().clean()
        if self.tipo == self.Tipo.CG:
            if not self.gruppo_id:
                raise ValidationError({"gruppo": "Obbligatorio per il ruolo CG."})
            if self.branca or self.settore:
                raise ValidationError("Il ruolo CG non usa branca né settore.")
        elif self.tipo == self.Tipo.IABZ:
            if not self.branca:
                raise ValidationError({"branca": "Obbligatoria per il ruolo IABZ."})
            if self.gruppo_id or self.settore:
                raise ValidationError("Il ruolo IABZ non usa gruppo né settore.")
        elif self.tipo == self.Tipo.ISZ:
            if not self.settore:
                raise ValidationError({"settore": "Obbligatorio per il ruolo ISZ."})
            if self.gruppo_id or self.branca:
                raise ValidationError("Il ruolo ISZ non usa gruppo né branca.")
        elif self.gruppo_id or self.branca or self.settore:
            raise ValidationError(f"Il ruolo {self.tipo} non usa gruppo, branca né settore.")

        if self.utente_id and not self._email_su_dominio_ammesso():
            raise ValidationError(
                "Un ruolo effettivo può essere assegnato solo a un utente con "
                f"email sui domini ammessi ({', '.join(settings.DOMINI_RUOLI_EFFETTIVI)}), "
                "D-04."
            )

    def _email_su_dominio_ammesso(self) -> bool:
        email = (self.utente.email or "").lower()
        return any(
            email.endswith(f"@{dominio.lower()}") for dominio in settings.DOMINI_RUOLI_EFFETTIVI
        )


class Delega(models.Model):
    """Delega di un ruolo effettivo, a iniziativa del titolare (D-04, D-26).
    Creata e revocata solo tramite il service layer in `apps/accounts/deleghe.py`."""

    delegante = models.ForeignKey(Utente, on_delete=models.CASCADE, related_name="deleghe_concesse")
    delegato = models.ForeignKey(Utente, on_delete=models.CASCADE, related_name="deleghe_ricevute")
    ruolo = models.ForeignKey(Ruolo, on_delete=models.CASCADE, related_name="deleghe")
    attiva = models.BooleanField(default=True)
    data_inizio = models.DateField(default=timezone.localdate)
    data_fine = models.DateField(help_text="Obbligatoria, a differenza del ruolo (D-04).")
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Delega"
        verbose_name_plural = "Deleghe"
        ordering = ["-data_inizio"]

    def __str__(self) -> str:
        return f"{self.delegante} → {self.delegato} ({self.ruolo})"

    @property
    def is_scaduta(self) -> bool:
        return self.data_fine < timezone.localdate()

    def clean(self):
        super().clean()
        if self.ruolo_id and self.delegante_id and self.ruolo.utente_id != self.delegante_id:
            raise ValidationError(
                "Un ruolo è delegabile solo dal suo titolare: un delegato non può "
                "a sua volta ri-delegare (D-04)."
            )
        if self.ruolo_id and self.ruolo.data_fine and self.data_fine > self.ruolo.data_fine:
            raise ValidationError(
                {"data_fine": "Non può eccedere la scadenza del ruolo di origine."}
            )
        if self.ruolo_id:
            max_deleghe = settings.MAX_DELEGHE_ATTIVE_PER_RUOLO
            attive = (
                Delega.objects.filter(ruolo_id=self.ruolo_id, attiva=True)
                .filter(Q(data_fine__gte=timezone.localdate()))
                .exclude(pk=self.pk)
                .count()
            )
            if self.attiva and not self.is_scaduta and attive >= max_deleghe:
                raise ValidationError(
                    f"Il ruolo ha già {attive} deleghe attive su {max_deleghe} "
                    "consentite (D-26)."
                )


class StatoInvito(models.TextChoices):
    INVIATO = "INVIATO", "Inviato"
    USATO = "USATO", "Usato"
    SCADUTO = "SCADUTO", "Scaduto"
    REVOCATO = "REVOCATO", "Revocato"


def _scadenza_default() -> datetime.datetime:
    return timezone.now() + datetime.timedelta(days=7)


ALFABETO_OTP = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


def genera_codice_otp(lunghezza: int = 8) -> str:
    return "".join(secrets.choice(ALFABETO_OTP) for _ in range(lunghezza))


class InvitoAttivazione(models.Model):
    """Attivazione tramite OTP su iniziativa della Zona (D-20), riusata per
    l'invito dei delegati (D-26) e per il recupero autonomo (D-25)."""

    email = models.EmailField()
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inviti_attivazione",
    )
    ruolo_proposto = models.CharField(
        max_length=10, choices=Ruolo.Tipo.choices, blank=True, default=""
    )
    delega_pendente = models.ForeignKey(
        Delega,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inviti",
    )
    codice_hash = models.CharField(max_length=128)
    stato = models.CharField(
        max_length=10, choices=StatoInvito.choices, default=StatoInvito.INVIATO
    )
    scadenza = models.DateTimeField(default=_scadenza_default)
    tentativi = models.PositiveSmallIntegerField(default=0)
    creato_da = models.ForeignKey(
        Utente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inviti_creati",
    )
    inviato_il = models.DateTimeField(null=True, blank=True)
    usato_il = models.DateTimeField(null=True, blank=True)

    MASSIMO_TENTATIVI = 5

    class Meta:
        verbose_name = "Invito di attivazione"
        verbose_name_plural = "Inviti di attivazione"
        ordering = ["-inviato_il"]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_stato_display()})"

    def imposta_codice(self, codice: str) -> None:
        self.codice_hash = make_password(codice)

    def verifica_codice(self, codice: str) -> bool:
        return check_password(codice, self.codice_hash)

    def aggiorna_stato_se_scaduto(self) -> None:
        if self.stato == StatoInvito.INVIATO and self.scadenza < timezone.now():
            self.stato = StatoInvito.SCADUTO
            self.save(update_fields=["stato"])


class SessioneImpersonificazione(models.Model):
    """Traccia inizio/fine di ogni impersonificazione (D-27), popolata dai segnali
    hijack_started/hijack_ended."""

    amministratore = models.ForeignKey(
        Utente, on_delete=models.CASCADE, related_name="sessioni_come_amministratore"
    )
    utente_impersonato = models.ForeignKey(
        Utente, on_delete=models.CASCADE, related_name="sessioni_subite"
    )
    iniziata_il = models.DateTimeField(auto_now_add=True)
    terminata_il = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Sessione di impersonificazione"
        verbose_name_plural = "Sessioni di impersonificazione"
        ordering = ["-iniziata_il"]

    def __str__(self) -> str:
        return (
            f"{self.amministratore} → {self.utente_impersonato} ({self.iniziata_il:%d/%m/%Y %H:%M})"
        )
