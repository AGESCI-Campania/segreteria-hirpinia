from django.apps import AppConfig


class AssembleeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assemblee"
    verbose_name = "Assemblee"

    def ready(self):
        from auditlog.registry import auditlog

        from .models import (
            Appello,
            Assemblea,
            AventeDiritto,
            Candidato,
            Candidatura,
            DelegaAE,
            IncaricoAssemblea,
            IncaricoDichiarato,
            OperatoreVoto,
            PosizioneVoto,
            Presenza,
            PuntoOdG,
            RigaProgramma,
            RisultatoCanale,
            Seduta,
            SottopuntoOdG,
            VariazioneRappresentante,
            VerbaleSeduta,
            Votazione,
        )

        # Eliminazioni, trasferimenti e nomine di operatori vanno tracciati (D-70):
        # la storia delle modifiche all'elenco sta nel log, non in campi duplicati.
        # Il registro delle operazioni dell'assemblea (registro.py) legge da qui:
        # un modello nuovo va registrato qui e in registro.GENITORE.
        auditlog.register(Assemblea)
        auditlog.register(Seduta)
        auditlog.register(AventeDiritto)
        auditlog.register(IncaricoDichiarato)
        auditlog.register(OperatoreVoto)
        auditlog.register(IncaricoAssemblea)
        auditlog.register(Appello)
        auditlog.register(Presenza)
        auditlog.register(DelegaAE)
        auditlog.register(PuntoOdG)
        auditlog.register(SottopuntoOdG)
        auditlog.register(Votazione)
        auditlog.register(RisultatoCanale)
        auditlog.register(Candidato)
        auditlog.register(VerbaleSeduta)
        auditlog.register(VariazioneRappresentante)
        auditlog.register(RigaProgramma)
        auditlog.register(PosizioneVoto)
        auditlog.register(Candidatura)
