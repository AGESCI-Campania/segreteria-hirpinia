"""Elenco e terminazione delle sessioni utente (M16), sopra
`allauth.usersessions.models.UserSession`: nessuna decodifica manuale di
`django_session`, il collegamento sessione->utente è già nel model (popolato
dal segnale `user_logged_in` di allauth, non da codice nostro)."""

from __future__ import annotations

from allauth.usersessions.models import UserSession
from django.contrib.auth import logout as django_logout
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from .models import Ruolo, Utente
from .permessi import ruoli_effettivi

# Escluso di proposito RDZ, a differenza di RUOLI_GESTIONE_RUOLI: la
# visibilità su tutte le sessioni di zona è riservata al livello
# amministrativo/segreteria, non a chi ha solo il ruolo di responsabile.
RUOLI_GESTIONE_SESSIONI = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA})


def sessioni_di(utente: Utente) -> list[UserSession]:
    """Sessioni ancora valide dell'utente, più recenti per prime. Le sessioni
    scadute/invalidate lato Django vengono scartate qui (`purge_and_list`,
    già fornito da allauth), non restano come righe fantasma."""
    sessioni = UserSession.objects.purge_and_list(utente)
    return sorted(sessioni, key=lambda s: s.created_at, reverse=True)


def tutte_le_sessioni() -> list[UserSession]:
    """Come `sessioni_di`, esteso a tutti gli utenti: stesso meccanismo di
    scarto delle sessioni scadute, una per una (`UserSession.purge()`)."""
    sessioni = []
    for sessione in UserSession.objects.select_related("user").all():
        if not sessione.purge():
            sessioni.append(sessione)
    return sorted(sessioni, key=lambda s: s.last_seen_at, reverse=True)


def _verifica_ruolo_gestione_sessioni(utente: Utente) -> None:
    ruoli = [r for r in ruoli_effettivi(utente) if not r.is_delega]
    if not any(r.tipo in RUOLI_GESTIONE_SESSIONI for r in ruoli):
        raise PermissionDenied(f"{utente}: azione riservata a SEGRETERIA/ADMIN diretti.")


def _termina(request: HttpRequest, sessione: UserSession) -> None:
    era_corrente = sessione.is_current()
    sessione.end()
    if era_corrente:
        django_logout(request)


def termina_sessione_propria(*, request: HttpRequest, sessione: UserSession) -> None:
    """Un utente termina una propria sessione: il perimetro è la proprietà
    della sessione, non un ruolo."""
    if sessione.user_id != request.user.pk:
        raise PermissionDenied("Non è una tua sessione.")
    _termina(request, sessione)


def termina_sessione_di_altri(*, request: HttpRequest, sessione: UserSession) -> None:
    """Admin/Segreteria terminano la sessione di un utente qualunque (D-27:
    il controllo è qui, nel service layer, non nel template)."""
    # RuoloRequiredMixin garantisce l'autenticazione prima di arrivare qui.
    assert isinstance(request.user, Utente)
    _verifica_ruolo_gestione_sessioni(request.user)
    _termina(request, sessione)
