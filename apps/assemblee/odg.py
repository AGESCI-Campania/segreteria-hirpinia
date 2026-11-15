"""Ordine del giorno dell'assemblea (D-70): punti liberi, con le proposte del
modello nazionale di verbale. Lo gestiscono ADMIN, SEGRETERIA e RdZ."""

from __future__ import annotations

from collections.abc import Sequence

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.models import Utente

from .models import Assemblea, PuntoOdG, SottopuntoOdG
from .permessi import puo_compilare_verbale, puo_gestire_assemblee

# Punti ricorrenti del modello nazionale di verbale dell'Assemblea di Zona.
PUNTI_TIPICI = [
    "Approvazione del Regolamento dell'Assemblea di Zona",
    "Definizione del numero di componenti del Comitato di Zona",
    "Elezione dei membri del Comitato di Zona e dei Consiglieri generali",
    "Discussione delle linee di indirizzo delle Azioni prioritarie regionali",
    "Discussione sugli orientamenti di politica associativa del livello nazionale e sui "
    "temi all'ordine del giorno del Consiglio generale",
    "Definizione dell'eventuale contributo economico aggiuntivo destinato alla Zona",
    "Approvazione del bilancio preventivo",
    "Approvazione delle eventuali variazioni al bilancio preventivo",
    "Varie ed eventuali",
]


def _verifica(utente: Utente, assemblea: Assemblea) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")


@transaction.atomic
def aggiungi_punto(assemblea: Assemblea, utente: Utente, titolo: str) -> PuntoOdG:
    _verifica(utente, assemblea)
    titolo = titolo.strip()
    if not titolo:
        raise ValidationError("Il punto deve avere un titolo.")
    ultimo = assemblea.punti_odg.aggregate(m=Max("ordine"))["m"] or 0
    return PuntoOdG.objects.create(assemblea=assemblea, ordine=ultimo + 1, titolo=titolo)


@transaction.atomic
def modifica_punto(punto: PuntoOdG, utente: Utente, *, titolo: str, testo: str) -> None:
    _verifica(utente, punto.assemblea)
    if not titolo.strip():
        raise ValidationError("Il punto deve avere un titolo.")
    punto.titolo = titolo.strip()
    punto.testo = testo.strip()
    punto.save(update_fields=["titolo", "testo"])


@transaction.atomic
def scrivi_discussione(punto: PuntoOdG, utente: Utente, testo: str) -> None:
    """La discussione del punto è parte del verbale: la scrivono anche
    presidenti e segretario, che non possono cambiare i punti (D12-bis). Si
    scrive anche ad assemblea conclusa, come il verbale."""
    if not puo_compilare_verbale(utente, punto.assemblea):
        raise PermissionDenied
    punto.testo = testo.strip()
    punto.save(update_fields=["testo"])


@transaction.atomic
def elimina_punto(punto: PuntoOdG, utente: Utente) -> None:
    """Le votazioni collegate restano, senza punto."""
    assemblea = punto.assemblea
    _verifica(utente, assemblea)
    punto.delete()
    _rinumera(assemblea)


@transaction.atomic
def sposta_punto(punto: PuntoOdG, utente: Utente, *, su: bool) -> None:
    _verifica(utente, punto.assemblea)
    punti = list(punto.assemblea.punti_odg.order_by("ordine"))
    i = punti.index(punto)
    j = i - 1 if su else i + 1
    if 0 <= j < len(punti):
        punti[i], punti[j] = punti[j], punti[i]
        _salva_ordine(punti)


def _rinumera(assemblea: Assemblea) -> None:
    _salva_ordine(list(assemblea.punti_odg.order_by("ordine")))


def _salva_ordine(punti: Sequence[PuntoOdG | SottopuntoOdG]) -> None:
    for numero, punto in enumerate(punti, start=1):
        if punto.ordine != numero:
            punto.ordine = numero
            punto.save(update_fields=["ordine"])


# --- Sottopunti: solo testo, discussione e votazioni restano sul punto ----------------


@transaction.atomic
def aggiungi_sottopunto(punto: PuntoOdG, utente: Utente, titolo: str) -> SottopuntoOdG:
    _verifica(utente, punto.assemblea)
    titolo = titolo.strip()
    if not titolo:
        raise ValidationError("Il sottopunto deve avere un titolo.")
    ultimo = punto.sottopunti.aggregate(m=Max("ordine"))["m"] or 0
    return SottopuntoOdG.objects.create(punto=punto, ordine=ultimo + 1, titolo=titolo)


@transaction.atomic
def modifica_sottopunto(sottopunto: SottopuntoOdG, utente: Utente, titolo: str) -> None:
    _verifica(utente, sottopunto.punto.assemblea)
    if not titolo.strip():
        raise ValidationError("Il sottopunto deve avere un titolo.")
    sottopunto.titolo = titolo.strip()
    sottopunto.save(update_fields=["titolo"])


@transaction.atomic
def elimina_sottopunto(sottopunto: SottopuntoOdG, utente: Utente) -> None:
    punto = sottopunto.punto
    _verifica(utente, punto.assemblea)
    sottopunto.delete()
    _salva_ordine(list(punto.sottopunti.order_by("ordine")))


@transaction.atomic
def sposta_sottopunto(sottopunto: SottopuntoOdG, utente: Utente, *, su: bool) -> None:
    _verifica(utente, sottopunto.punto.assemblea)
    sottopunti = list(sottopunto.punto.sottopunti.order_by("ordine"))
    i = sottopunti.index(sottopunto)
    j = i - 1 if su else i + 1
    if 0 <= j < len(sottopunti):
        sottopunti[i], sottopunti[j] = sottopunti[j], sottopunti[i]
        _salva_ordine(sottopunti)
