"""Voto elettronico per le elezioni (docs/plan_voto.md, futura D-71).

Unica superficie pubblica senza login del progetto: i modelli qui non
scrivono mai `Capo`, `CensimentoCapo` o `IncaricoUnita` (D-70) e nessuno è
registrato in auditlog (codici, schede e votanti non devono finire nei log).
Emissione e revoca dei codici restano tracciate dai campi del modello."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CodiceVoto(models.Model):
    """Codice di voto di un avente diritto per una seduta. Si salva **solo
    l'hash** (come l'OTP di attivazione, D-20): il codice in chiaro si vede
    una volta sola, nell'email o sullo schermo del banco. Rigenerarlo revoca
    il precedente."""

    seduta = models.ForeignKey(
        "assemblee.Seduta", on_delete=models.CASCADE, related_name="codici_voto"
    )
    avente = models.ForeignKey(
        "assemblee.AventeDiritto", on_delete=models.CASCADE, related_name="codici_voto"
    )
    hash = models.CharField(max_length=64, unique=True)
    emesso_il = models.DateTimeField(auto_now_add=True)
    emesso_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    inviato_per_email = models.BooleanField(default=False)
    revocato_il = models.DateTimeField(null=True, blank=True)
    revocato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "codice di voto"
        verbose_name_plural = "codici di voto"
        ordering = ["-emesso_il"]
        constraints = [
            models.UniqueConstraint(
                fields=["seduta", "avente"],
                condition=Q(revocato_il__isnull=True),
                name="un_codice_attivo_per_avente_e_seduta",
            )
        ]

    def __str__(self) -> str:
        return f"Codice di {self.avente} — {self.seduta}"

    @property
    def attivo(self) -> bool:
        return self.revocato_il is None


class Votante(models.Model):
    """«Chi ha votato» in app: pubblico per regolamento, a differenza di cosa
    ha votato. **Nessun timestamp** e nessun legame con la `Scheda`: insieme
    all'ordine casuale delle schede alla chiusura è ciò che impedisce di
    ricollegare un voto a chi l'ha espresso. `tramite` è il delegato che ha
    votato per conto di un AE (art. 5)."""

    votazione = models.ForeignKey(
        "assemblee.Votazione", on_delete=models.CASCADE, related_name="votanti_app"
    )
    avente = models.ForeignKey(
        "assemblee.AventeDiritto", on_delete=models.PROTECT, related_name="voti_app"
    )
    tramite = models.ForeignKey(
        "assemblee.AventeDiritto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voti_app_per_delega",
    )

    class Meta:
        verbose_name = "votante in app"
        verbose_name_plural = "votanti in app"
        constraints = [
            models.UniqueConstraint(fields=["votazione", "avente"], name="un_voto_per_avente")
        ]

    def __str__(self) -> str:
        return f"{self.avente} — {self.votazione}"


class Scheda(models.Model):
    """Una scheda nell'urna elettronica. **Nessuna FK** ad avente, codice o
    votante e **nessun timestamp**: id casuale, ricevuta casuale. `scelte`:
    {"esito": "VOTO"|"BIANCA"|"NULLA", "candidati": [id], "liberi": [testo]}.
    `interpretazione` (dalla chiusura): per ogni nome libero, l'id del
    candidato a cui la commissione lo attribuisce, oppure null se nullo."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    votazione = models.ForeignKey(
        "assemblee.Votazione", on_delete=models.CASCADE, related_name="schede_app"
    )
    ricevuta = models.CharField(max_length=20, unique=True)
    scelte = models.JSONField()
    interpretazione = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "scheda"
        verbose_name_plural = "schede"
        # Nessun ordinamento significativo: l'ordine non deve dire nulla.
        ordering = ["ricevuta"]

    def __str__(self) -> str:
        return f"Scheda {self.ricevuta}"


class InterpretazioneNome(models.Model):
    """Decisione della commissione elettorale su un nome scritto in una
    scheda, per testo (lo stesso testo vale uguale in tutte le schede):
    attribuito a un avente diritto, oppure nullo (`avente` vuoto). Il testo
    resta qui, visibile solo a chi gestisce lo scrutinio; bacheca e verbale
    riportano solo l'interpretazione. Non collega alcuna scheda."""

    votazione = models.ForeignKey(
        "assemblee.Votazione", on_delete=models.CASCADE, related_name="interpretazioni_nomi"
    )
    chiave = models.CharField(max_length=100)
    avente = models.ForeignKey(
        "assemblee.AventeDiritto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    decisa_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    decisa_il = models.DateTimeField()

    class Meta:
        verbose_name = "interpretazione di un nome scritto"
        verbose_name_plural = "interpretazioni dei nomi scritti"
        constraints = [
            models.UniqueConstraint(
                fields=["votazione", "chiave"], name="una_interpretazione_per_nome"
            )
        ]

    def __str__(self) -> str:
        return f"{self.chiave} → {self.avente or 'nullo'}"
