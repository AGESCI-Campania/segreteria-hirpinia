from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

PERCORSI_ESCLUSI = ("/accounts/", "/hijack/", "/static/", "/media/", "/admin/")

CHIAVE_SESSIONE_ULTIMA_ATTIVITA = "ultima_attivita"


def _percorso_escluso(path: str) -> bool:
    return any(path.startswith(prefisso) for prefisso in PERCORSI_ESCLUSI)


class SessionInactivityMiddleware:
    """Disconnette l'utente autenticato dopo un periodo di inattività
    configurabile da interfaccia (`ImpostazioniPiattaforma.durata_inattivita_minuti`).
    Timeout scorrevole: ogni richiesta autenticata aggiorna il timestamp di
    ultima attività salvato nella sessione stessa, non in un model esterno."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not _percorso_escluso(request.path):
            ora = timezone.now().timestamp()
            ultima_attivita = request.session.get(CHIAVE_SESSIONE_ULTIMA_ATTIVITA)
            if ultima_attivita is not None:
                timeout_secondi = self._timeout_minuti() * 60
                if ora - ultima_attivita > timeout_secondi:
                    logout(request)
                    messages.info(request, "Sessione scaduta per inattività: accedi di nuovo.")
                    return redirect(settings.LOGIN_URL)
            request.session[CHIAVE_SESSIONE_ULTIMA_ATTIVITA] = ora
        return self.get_response(request)

    @staticmethod
    def _timeout_minuti() -> int:
        from apps.core.models import ImpostazioniPiattaforma

        valore = (
            ImpostazioniPiattaforma.objects.filter(pk=1)
            .values_list("durata_inattivita_minuti", flat=True)
            .first()
        )
        if valore is not None:
            return valore
        return ImpostazioniPiattaforma._meta.get_field("durata_inattivita_minuti").default


class StatoUtenteMiddleware:
    """Un utente IN_ATTESA o SOSPESO può autenticarsi ma non accede ai moduli
    (D-06): vede solo una pagina di cortesia. Stesso principio per un account
    funzionale di gruppo il cui gruppo non è più attivo (D-24): "l'account
    funzionale del gruppo non può più autenticarsi" si traduce qui, come per
    IN_ATTESA/SOSPESO, in "autentica ma vede solo una pagina di cortesia"."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import StatoUtente, TipoUtente

        if request.user.is_authenticated and not _percorso_escluso(request.path):
            if getattr(request.user, "stato", StatoUtente.ATTIVO) != StatoUtente.ATTIVO:
                return redirect(reverse("accounts:attesa"))
            if self._gruppo_non_attivo(request.user, TipoUtente):
                return redirect(reverse("accounts:gruppo_non_attivo"))
        return self.get_response(request)

    @staticmethod
    def _gruppo_non_attivo(utente, tipo_utente) -> bool:
        from apps.organizzazione.models import anno_scout_corrente

        if utente.tipo != tipo_utente.GRUPPO or not utente.gruppo_id:
            return False
        return not utente.gruppo.e_attivo(anno_scout_corrente())


class MFAEnforcementMiddleware:
    """Chi detiene direttamente (non per delega) un ruolo in
    RUOLI_MFA_OBBLIGATORIA deve configurare il secondo fattore prima di
    accedere ai moduli (D-05, D-20)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not _percorso_escluso(request.path)
            and self._richiede_mfa_non_configurata(request)
        ):
            return redirect(reverse("mfa_activate_totp"))
        return self.get_response(request)

    @staticmethod
    def _richiede_mfa_non_configurata(request) -> bool:
        from allauth.mfa.adapter import get_adapter as get_mfa_adapter
        from allauth.mfa.models import Authenticator

        from .permessi import ruoli_effettivi

        ruoli_obbligati = settings.RUOLI_MFA_OBBLIGATORIA
        ha_ruolo_obbligato = any(
            r.tipo in ruoli_obbligati and not r.is_delega for r in ruoli_effettivi(request.user)
        )
        if not ha_ruolo_obbligato:
            return False
        return not get_mfa_adapter().is_mfa_enabled(request.user, types=[Authenticator.Type.TOTP])
