from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Account"

    def ready(self):
        from auditlog.registry import auditlog

        from . import signals  # noqa: F401
        from .models import Delega, Ruolo, Utente

        auditlog.register(Utente)
        auditlog.register(Ruolo)
        auditlog.register(Delega)
