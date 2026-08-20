from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter
from django.conf import settings

from apps.organizzazione.models import AllowlistGruppo

from .models import Ruolo, StatoUtente, TipoUtente


class CatelloAccountAdapter(DefaultAccountAdapter):
    """Flusso di registrazione autonoma (D-06): un'email in allowlist attiva
    subito l'account come account di gruppo; altrimenti l'utente resta
    IN_ATTESA finché la segreteria non lo associa a un gruppo."""

    def is_open_for_signup(self, request) -> bool:
        return True

    def save_user(self, request, user, form, commit: bool = True):
        user = super().save_user(request, user, form, commit=False)

        voce = AllowlistGruppo.risolvi(user.email)
        if voce is not None:
            user.tipo = TipoUtente.GRUPPO
            user.gruppo_id = voce.codice_gruppo
            user.stato = StatoUtente.ATTIVO
        else:
            user.tipo = TipoUtente.PERSONA
            user.stato = StatoUtente.IN_ATTESA

        if commit:
            user.full_clean(exclude=["password"])
            user.save()
            if voce is not None:
                Ruolo.objects.create(
                    utente=user,
                    tipo=Ruolo.Tipo.CG,
                    gruppo_id=voce.codice_gruppo,
                    origine=Ruolo.Origine.AMMINISTRATIVO,
                )
        return user


class CatelloMFAAdapter(DefaultMFAAdapter):
    """Nessun bypass della MFA: a differenza di eventuali piattaforme collegate
    a uno SSO, Catello non ha alcuna alternativa al secondo fattore (D-05).
    Impedisce la disattivazione del TOTP ai ruoli per cui è obbligatoria."""

    def can_delete_authenticator(self, authenticator) -> bool:
        from allauth.mfa.models import Authenticator

        if authenticator.type != Authenticator.Type.TOTP:
            return True

        from .permessi import ruoli_effettivi

        utente = authenticator.user
        ruoli_obbligati = settings.RUOLI_MFA_OBBLIGATORIA
        ha_ruolo_obbligato = any(
            r.tipo in ruoli_obbligati and not r.is_delega for r in ruoli_effettivi(utente)
        )
        if not ha_ruolo_obbligato:
            return True

        altri_totp = (
            Authenticator.objects.filter(user=utente, type=Authenticator.Type.TOTP)
            .exclude(pk=authenticator.pk)
            .exists()
        )
        return altri_totp
