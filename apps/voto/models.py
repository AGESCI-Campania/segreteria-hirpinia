"""Voto elettronico per le elezioni (docs/plan_voto.md, futura D-71).

Unica superficie pubblica senza login del progetto: i modelli qui non
scrivono mai `Capo`, `CensimentoCapo` o `IncaricoUnita` (D-70) e nessuno è
registrato in auditlog (codici, schede e votanti non devono finire nei log).
Emissione e revoca dei codici restano tracciate dai campi del modello."""

from __future__ import annotations

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
