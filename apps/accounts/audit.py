"""Impersonificazione (D-27): azioni precluse enforced nel service layer, mai
solo nascondendo un pulsante nel template; doppia identità nell'audit."""

import functools

from auditlog.middleware import AuditlogMiddleware
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

# campagna_chiudi/campagna_liquida restano definite ma inapplicate finché
# `contributi` non esiste (M4+): l'elenco è già completo per non doverlo
# ripensare quando quell'app arriverà.
AZIONI_PRECLUSE_IN_HIJACK = frozenset(
    {
        "modifica_iban",
        "modifica_intestazione_conto",
        "modifica_password",
        "modifica_email",
        "modifica_mfa",
        "cancellazione",
        "campagna_chiudi",
        "campagna_liquida",
    }
)


def _e_impersonificato(request) -> bool:
    return bool(request is not None and request.session.get("hijack_history"))


def vieta_in_impersonificazione(azione: str):
    """Decoratore per funzioni del service layer che accettano `request` come
    primo argomento posizionale o come kwarg. Solleva PermissionDenied se
    l'utente corrente sta operando in impersonificazione."""
    if azione not in AZIONI_PRECLUSE_IN_HIJACK:
        raise ValueError(f"Azione non riconosciuta: {azione!r}")

    def decoratore(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            if _e_impersonificato(request):
                raise PermissionDenied(
                    f"Azione '{azione}' preclusa durante l'impersonificazione (D-27)."
                )
            return func(request, *args, **kwargs)

        return wrapper

    return decoratore


class CatelloAuditlogMiddleware(AuditlogMiddleware):
    """Aggiunge l'identità reale dell'amministratore, quando presente, a ogni
    voce di audit scritta durante un'impersonificazione (D-27): `LogEntry.actor`
    resta l'utente impersonato (comportamento nativo di allauth+hijack, che
    sostituisce request.user), l'identità reale finisce in
    additional_data["eseguito_da_reale"]."""

    def get_extra_data(self, request):
        dati = super().get_extra_data(request)
        history = request.session.get("hijack_history") if hasattr(request, "session") else None
        if history:
            utente_reale = get_user_model().objects.filter(pk=history[-1]).first()
            if utente_reale is not None:
                dati["eseguito_da_reale"] = str(utente_reale)
        return dati
