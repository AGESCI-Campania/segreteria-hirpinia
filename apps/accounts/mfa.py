"""Tipi di secondo fattore che soddisfano l'obbligo MFA (D-05, issue #10).

Unico punto di verità, usato sia dall'enforcement (middleware.py) sia dal
controllo di cancellazione degli authenticator (adapters.py): se la regola
cambia, cambia qui soltanto.
"""

from django.conf import settings

from .permessi import ruoli_effettivi


def tipi_mfa_accettati(utente) -> frozenset[str]:
    """Tipi di ``Authenticator`` che, se configurati, soddisfano l'obbligo MFA
    per i ruoli diretti (non per delega) dell'utente. Vuoto se l'utente non ha
    alcun ruolo obbligato.

    ADMIN/SEGRETERIA accettano anche il WebAuthn (passkey); RDZ resta
    vincolato al solo TOTP. Un utente con ruoli diretti multipli (es. RDZ e
    anche ADMIN) è coperto dall'insieme più ampio: ADMIN/SEGRETERIA vincono
    sempre, non RDZ.
    """
    from allauth.mfa.models import Authenticator

    ruoli_diretti = {r.tipo for r in ruoli_effettivi(utente) if not r.is_delega}
    ruoli_obbligati = ruoli_diretti & settings.RUOLI_MFA_OBBLIGATORIA
    if not ruoli_obbligati:
        return frozenset()

    tipi = {Authenticator.Type.TOTP}
    if ruoli_obbligati & settings.RUOLI_MFA_ACCETTA_PASSKEY:
        tipi.add(Authenticator.Type.WEBAUTHN)
    return frozenset(tipi)
