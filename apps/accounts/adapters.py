from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter

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
    Impedisce la cancellazione dell'ultimo fattore fra quelli accettati per il
    ruolo dell'utente (TOTP, e per ADMIN/SEGRETERIA anche WebAuthn — issue
    #10): i recovery codes non contano come fattore a sé, restano il fallback
    per quando si perde l'accesso al fattore principale."""

    def can_delete_authenticator(self, authenticator) -> bool:
        from allauth.mfa.models import Authenticator

        from .mfa import tipi_mfa_accettati

        tipi_accettati = tipi_mfa_accettati(authenticator.user)
        if authenticator.type not in tipi_accettati:
            return True

        altri = (
            Authenticator.objects.filter(user=authenticator.user, type__in=tipi_accettati)
            .exclude(pk=authenticator.pk)
            .exists()
        )
        return altri
