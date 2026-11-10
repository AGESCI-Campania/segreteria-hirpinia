from django.apps import AppConfig


class AssembleeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assemblee"
    verbose_name = "Assemblee"

    def ready(self):
        from auditlog.registry import auditlog

        from .models import Assemblea, AventeDiritto, IncaricoDichiarato, OperatoreVoto, Seduta

        # Eliminazioni, trasferimenti e nomine di operatori vanno tracciati (D-70):
        # la storia delle modifiche all'elenco sta nel log, non in campi duplicati.
        auditlog.register(Assemblea)
        auditlog.register(Seduta)
        auditlog.register(AventeDiritto)
        auditlog.register(IncaricoDichiarato)
        auditlog.register(OperatoreVoto)
