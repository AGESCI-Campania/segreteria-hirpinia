"""Configurazione di piattaforma (A-5): modello singleton, pattern minimale
senza libreria esterna — `pk` fisso a 1, `corrente()` come unico punto di
accesso. Solo `causale_bonifico_default` per ora: gli altri campi descritti
nel documento di progettazione (`tetto_partecipazione_default`,
`email_segreteria`, `manutenzione`) non hanno ancora nessuna funzionalità
collegata in nessuna milestone del piano — verranno aggiunti quando servirà
davvero, non prima (CLAUDE.md: niente implementazioni a metà)."""

from __future__ import annotations

from django.db import models


class ImpostazioniPiattaforma(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    causale_bonifico_default = models.CharField(max_length=200, blank=True)

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


__all__ = ["ImpostazioniPiattaforma"]
