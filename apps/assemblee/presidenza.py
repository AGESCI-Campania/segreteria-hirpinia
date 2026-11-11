"""Ufficio di presidenza e comitati dell'assemblea, indicati in preparazione
(docs/plan_preparazione_assemblea.md, R4, D7-D12). Unico punto per
aggiungerli, toglierli e dar loro l'accesso.

- Presidenti (al massimo due, di sesso diverso), segretario (uno), comitato
  mozioni (sempre tre, raccolti fino a tre), scrutatori (due, scelti fra i
  componenti del comitato elettorale).
- Solo aventi diritto dell'elenco (D8).
- Presidenti e segretario possono avere l'accesso a Catello (account e invito
  come per il comitato elettorale, D12): vedono risultati, presenze e ordine
  del giorno, compilano il verbale (`permessi.puo_compilare_verbale()`).
- Precompilano il verbale di ogni seduta, dove restano modificabili (D7)."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import Utente

from . import comitato
from .models import (
    POSTI_RUOLO_ASSEMBLEA,
    RUOLI_CON_ACCESSO,
    Assemblea,
    AventeDiritto,
    IncaricoAssemblea,
    RuoloAssemblea,
)
from .permessi import puo_gestire_assemblee


def _verifica(utente: Utente, assemblea: Assemblea) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa.")


def incarichi(assemblea: Assemblea, ruolo: str | None = None):
    qs = assemblea.incarichi.select_related("avente", "avente__gruppo", "utente").order_by(
        "nominato_il"
    )
    return qs.filter(ruolo=ruolo) if ruolo else qs


def nomi(assemblea: Assemblea, ruolo: str) -> list[str]:
    return [f"{i.avente.cognome} {i.avente.nome}" for i in incarichi(assemblea, ruolo)]


def aggiungi(
    assemblea: Assemblea,
    ruolo: str,
    avente: AventeDiritto,
    gestore: Utente,
    *,
    accesso: bool = True,
) -> tuple[IncaricoAssemblea, bool]:
    """Restituisce l'incarico e se è partito un invito di attivazione.
    `accesso` vale solo per presidenti e segretario."""
    _verifica(gestore, assemblea)
    if ruolo not in RuoloAssemblea.values:
        raise ValidationError("Ruolo non valido.")
    if avente.assemblea_id != assemblea.pk or avente.eliminato_il is not None:
        raise ValidationError("Il capo non è nell'elenco degli aventi diritto.")
    with transaction.atomic():
        attuali = list(incarichi(assemblea, ruolo))
        if any(i.avente_id == avente.pk for i in attuali):
            raise ValidationError(f"{avente} ha già questo incarico.")
        posti = POSTI_RUOLO_ASSEMBLEA[RuoloAssemblea(ruolo)]
        if len(attuali) >= posti:
            raise ValidationError(
                f"{RuoloAssemblea(ruolo).label}: al massimo {posti}, già tutti indicati."
            )
        if (
            ruolo == RuoloAssemblea.SCRUTATORE
            and not assemblea.operatori.filter(avente=avente).exists()
        ):
            raise ValidationError(
                "Gli scrutatori si scelgono fra i componenti del comitato elettorale."
            )
        if ruolo == RuoloAssemblea.PRESIDENTE and avente.sesso:
            if any(i.avente.sesso == avente.sesso for i in attuali):
                raise ValidationError("I due presidenti devono essere di sesso diverso.")
        incarico = IncaricoAssemblea.objects.create(
            assemblea=assemblea, ruolo=ruolo, avente=avente, nominato_da=gestore
        )
        utente = None
        if accesso and ruolo in RUOLI_CON_ACCESSO:
            utente = comitato.account_per_avente(avente)
            incarico.utente = utente
            incarico.save(update_fields=["utente"])
    return incarico, utente is not None and comitato.invia_invito(utente, gestore, assemblea)


def dai_accesso(incarico: IncaricoAssemblea, gestore: Utente) -> bool:
    """Crea l'account a un presidente o segretario che non l'ha, o rimanda
    l'invito a chi non ha ancora la password. Restituisce se è partito."""
    _verifica(gestore, incarico.assemblea)
    if incarico.ruolo not in RUOLI_CON_ACCESSO:
        raise ValidationError("Solo presidenti e segretario hanno un accesso.")
    with transaction.atomic():
        utente = incarico.utente
        if utente is None:
            utente = comitato.account_per_avente(incarico.avente)
            incarico.utente = utente
            incarico.save(update_fields=["utente"])
    return comitato.invia_invito(utente, gestore, incarico.assemblea)


@transaction.atomic
def rimuovi(incarico: IncaricoAssemblea, gestore: Utente) -> None:
    """Toglie l'incarico; l'account resta, senza più accesso all'assemblea."""
    _verifica(gestore, incarico.assemblea)
    incarico.delete()


@dataclass(frozen=True)
class Avviso:
    testo: str


def avvisi(assemblea: Assemblea) -> list[Avviso]:
    """Situazioni da completare, non bloccanti."""
    risultato = []
    presidenti = list(incarichi(assemblea, RuoloAssemblea.PRESIDENTE))
    if not presidenti:
        risultato.append(Avviso("Presidenza non ancora indicata."))
    elif len(presidenti) == 2 and not all(p.avente.sesso for p in presidenti):
        risultato.append(
            Avviso(
                "Sesso di un presidente non noto: non si può verificare che siano di sesso diverso."
            )
        )
    if not incarichi(assemblea, RuoloAssemblea.SEGRETARIO).exists():
        risultato.append(Avviso("Segretario non ancora indicato."))
    mozioni = incarichi(assemblea, RuoloAssemblea.MOZIONI).count()
    if mozioni < POSTI_RUOLO_ASSEMBLEA[RuoloAssemblea.MOZIONI]:
        risultato.append(Avviso(f"Comitato mozioni: {mozioni} membri su 3."))
    scrutatori = incarichi(assemblea, RuoloAssemblea.SCRUTATORE).count()
    if scrutatori < POSTI_RUOLO_ASSEMBLEA[RuoloAssemblea.SCRUTATORE]:
        risultato.append(Avviso(f"Scrutatori: {scrutatori} su 2."))
    return risultato


def dati_per_verbale(assemblea: Assemblea) -> dict[str, str]:
    """Valori con cui la preparazione precompila il verbale di una seduta."""
    presidenti = nomi(assemblea, RuoloAssemblea.PRESIDENTE)
    scrutatori = nomi(assemblea, RuoloAssemblea.SCRUTATORE)
    return {
        "presidente": presidenti[0] if presidenti else "",
        "presidente_2": presidenti[1] if len(presidenti) > 1 else "",
        "segretario": ", ".join(nomi(assemblea, RuoloAssemblea.SEGRETARIO)),
        "comitato_mozioni": ", ".join(nomi(assemblea, RuoloAssemblea.MOZIONI)),
        "scrutatore_1": scrutatori[0] if scrutatori else "",
        "scrutatore_2": scrutatori[1] if len(scrutatori) > 1 else "",
    }
