"""Riepilogo per gruppo dello stato di invio del contributo Fo.Ca. (issue
#11): a differenza di `apps/contributi/riepilogo.py` (aggregato di
campagna, richiede CHIUSA/LIQUIDATA), questo riepilogo è per singolo gruppo
e funziona anche a campagna APERTA — serve a chi segue la campagna per capire
chi manca prima della chiusura. Non contiene dati sensibili (mai il valore
dell'IBAN, solo un booleano di presenza) e per questo è mostrato per intero a
chiunque acceda alla pagina, senza filtrare i gruppi per perimetro di ruolo."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum

from apps.accounts.models import TipoUtente, Utente
from apps.accounts.permessi import gruppi_visibili
from apps.organizzazione.models import Gruppo

from .models import (
    Campagna,
    ContributoPartecipazione,
    DichiarazioneNessunRimborso,
    Partecipazione,
    StatoCampagna,
)
from .visibilita import STATI_CON_VISIBILITA_CROSS_GRUPPO


class StatoSemaforo(Enum):
    VERDE = "verde"
    GIALLO = "giallo"
    ROSSO = "rosso"


@dataclass(frozen=True)
class RiepilogoGruppo:
    gruppo_codice: str
    gruppo_nome: str
    account_attivato: bool
    iban_caricato: bool
    capi_inseriti: int
    nessun_rimborso_dichiarato: bool
    stato: StatoSemaforo
    contributo_ricevuto: Decimal | None


def _stato_semaforo(
    *, iban_caricato: bool, capi_inseriti: int, nessun_rimborso_dichiarato: bool
) -> StatoSemaforo:
    """Issue #16: `account_attivato` non entra nel calcolo (mostrata in
    tabella, ma non usata nel computo, per esplicita richiesta della issue) e
    la dichiarazione "nessun rimborso" prevale incondizionatamente sull'IBAN
    mancante — se il gruppo non riceve soldi, l'IBAN è irrilevante."""
    if nessun_rimborso_dichiarato:
        return StatoSemaforo.VERDE
    capi_ok = capi_inseriti > 0
    if iban_caricato and capi_ok:
        return StatoSemaforo.VERDE
    if not iban_caricato and not capi_ok:
        return StatoSemaforo.ROSSO
    return StatoSemaforo.GIALLO


def riepilogo_gruppi(campagna: Campagna) -> list[RiepilogoGruppo]:
    gruppi = list(
        Gruppo.objects.attivi(campagna.anno).exclude(is_comitato_zona=True).order_by("nome")
    )

    account_attivati = set(
        Utente.objects.filter(
            tipo=TipoUtente.GRUPPO, gruppo__in=gruppi, last_login__isnull=False
        ).values_list("gruppo_id", flat=True)
    )
    capi_per_gruppo = {
        riga["gruppo_id"]: riga["n"]
        for riga in Partecipazione.objects.filter(campagna=campagna, gruppo__in=gruppi)
        .values("gruppo_id")
        .annotate(n=Count("capo_id", distinct=True))
    }
    dichiarazioni = set(
        DichiarazioneNessunRimborso.objects.filter(campagna=campagna).values_list(
            "gruppo_id", flat=True
        )
    )
    contributi_per_gruppo: dict[str, Decimal] = {}
    if campagna.stato in STATI_CON_VISIBILITA_CROSS_GRUPPO:
        contributi_per_gruppo = {
            riga["partecipazione__gruppo_id"]: riga["tot"]
            for riga in ContributoPartecipazione.objects.filter(
                partecipazione__campagna=campagna,
                partecipazione__gruppo__in=gruppi,
                is_simulazione=False,
            )
            .values("partecipazione__gruppo_id")
            .annotate(tot=Sum("importo"))
        }

    righe = []
    for gruppo in gruppi:
        account_attivato = gruppo.codice in account_attivati
        iban_caricato = bool(gruppo.iban)
        capi_inseriti = capi_per_gruppo.get(gruppo.codice, 0)
        nessun_rimborso_dichiarato = gruppo.codice in dichiarazioni
        stato = _stato_semaforo(
            iban_caricato=iban_caricato,
            capi_inseriti=capi_inseriti,
            nessun_rimborso_dichiarato=nessun_rimborso_dichiarato,
        )
        righe.append(
            RiepilogoGruppo(
                gruppo_codice=gruppo.codice,
                gruppo_nome=gruppo.nome,
                account_attivato=account_attivato,
                iban_caricato=iban_caricato,
                capi_inseriti=capi_inseriti,
                nessun_rimborso_dichiarato=nessun_rimborso_dichiarato,
                stato=stato,
                contributo_ricevuto=contributi_per_gruppo.get(gruppo.codice),
            )
        )
    return righe


def _verifica_permesso_gruppo(utente: Utente, campagna: Campagna, gruppo: Gruppo) -> None:
    visibili = {g.codice for g in gruppi_visibili(utente, campagna.anno)}
    if gruppo.codice not in visibili:
        raise PermissionDenied(f"{gruppo.codice} non è nel perimetro di {utente}.")


def dichiara_nessun_rimborso(
    *, utente: Utente, campagna: Campagna, gruppo: Gruppo
) -> DichiarazioneNessunRimborso:
    _verifica_permesso_gruppo(utente, campagna, gruppo)
    if campagna.stato != StatoCampagna.APERTA:
        raise ValidationError("La dichiarazione è possibile solo a campagna aperta.")
    if Partecipazione.objects.filter(campagna=campagna, gruppo=gruppo).exists():
        raise ValidationError(
            "Il gruppo ha già partecipazioni inserite per questa campagna: "
            "la dichiarazione non è coerente."
        )
    dichiarazione, _ = DichiarazioneNessunRimborso.objects.update_or_create(
        campagna=campagna, gruppo=gruppo, defaults={"dichiarata_da": utente}
    )
    return dichiarazione


def revoca_dichiarazione_nessun_rimborso(
    *, utente: Utente, campagna: Campagna, gruppo: Gruppo
) -> None:
    _verifica_permesso_gruppo(utente, campagna, gruppo)
    DichiarazioneNessunRimborso.objects.filter(campagna=campagna, gruppo=gruppo).delete()
