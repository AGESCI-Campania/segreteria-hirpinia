"""Configurazione di piattaforma (A-5): modello singleton, pattern minimale
senza libreria esterna — `pk` fisso a 1, `corrente()` come unico punto di
accesso. Solo `causale_bonifico_default` per ora: gli altri campi descritti
nel documento di progettazione (`tetto_partecipazione_default`,
`email_segreteria`, `manutenzione`) non hanno ancora nessuna funzionalità
collegata in nessuna milestone del piano — verranno aggiunti quando servirà
davvero, non prima (CLAUDE.md: niente implementazioni a metà)."""

from __future__ import annotations

from django.db import models


class CodiceTemplateEmail(models.TextChoices):
    """Chiave stabile per ciascuno dei 6 flussi di invio esistenti (M8):
    corrisponde 1:1 ai punti di invio in `apps/accounts/inviti.py`,
    `apps/accounts/deleghe.py`, `apps/accounts/signals.py`,
    `apps/anagrafica/incarichi.py`. Vocabolario chiuso: nessun sesto/settimo
    valore va aggiunto senza collegarlo a un vero punto di invio."""

    INVITO_ATTIVAZIONE = "invito_attivazione", "Invito di attivazione"
    FINE_IMPERSONIFICAZIONE = "fine_impersonificazione", "Fine impersonificazione"
    DELEGA_CREATA = "delega_creata", "Delega creata"
    DELEGA_REVOCATA = "delega_revocata", "Delega revocata"
    INCARICO_ASSEGNATO = "incarico_assegnato", "Incarico assegnato"
    INCARICO_CESSATO = "incarico_cessato", "Incarico cessato"


class TemplateEmail(models.Model):
    """Template email configurabile da interfaccia (M8): sostituisce il
    contenuto hardcoded degli invii esistenti. `corpo_html` è renderizzato
    con un motore di sostituzione ridotto (`apps/core/template_email.py`,
    solo placeholder `{{ variabile }}`, mai tag Django) e sanitizzato con
    bleach prima dell'invio — mai il motore template completo di Django, per
    non ampliare la superficie di attacco di un contenuto che ora arriva da
    un form invece che da un file sotto controllo di versione. `corpo_testo`
    è il fallback plain-text, sempre presente in ogni invio multipart."""

    codice = models.CharField(max_length=30, choices=CodiceTemplateEmail.choices, unique=True)
    oggetto = models.CharField(max_length=200)
    corpo_html = models.TextField(blank=True)
    corpo_testo = models.TextField(blank=True)

    class Meta:
        verbose_name = "Template email"
        verbose_name_plural = "Template email"
        ordering = ["codice"]

    def __str__(self) -> str:
        return self.get_codice_display()


class ImpostazioniPiattaforma(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    causale_bonifico_default = models.CharField(max_length=200, blank=True)
    email_su_mailpit = models.BooleanField(
        default=False,
        verbose_name="Invia le email su Mailpit invece del provider configurato",
        help_text=(
            "Solo in produzione (apps.core.email.override.MailpitOverridableBackend): "
            "reindirizza ogni email verso Mailpit invece di consegnarla davvero. "
            "Richiede EMAIL_MAILPIT_HOST configurato."
        ),
    )

    class Meta:
        verbose_name = "Impostazioni piattaforma"
        verbose_name_plural = "Impostazioni piattaforma"

    def __str__(self) -> str:
        return "Impostazioni piattaforma"

    def save(self, *args, **kwargs) -> None:
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def corrente(cls) -> ImpostazioniPiattaforma:
        return cls.objects.get_or_create(pk=1)[0]


__all__ = ["CodiceTemplateEmail", "ImpostazioniPiattaforma", "TemplateEmail"]
