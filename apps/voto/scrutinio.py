"""Apertura, chiusura e scrutinio dell'urna elettronica (docs/plan_voto.md,
flusso 4): unico punto delle regole.

- Una sola urna aperta per seduta. Durante il voto si vede solo il numero dei
  votanti, mai risultati parziali.
- Alla chiusura: verifica bloccante schede = votanti, poi **rimescolamento**
  (le schede si riscrivono in ordine casuale con id nuovi, in un'unica
  transazione), che cancella la traccia fisica dell'ordine di inserimento.
- I nomi scritti li interpreta la commissione elettorale, per testo: a un
  avente diritto (che diventa candidato, se non lo era) o nullo. Finché ne
  resta uno da interpretare il conteggio non si fa. In bacheca e nel verbale
  compare solo l'interpretazione, mai il testo scritto.
- Il conteggio sostituisce l'inserimento a mano dei voti in app: lo usa
  `votazioni.registra_risultati()`; esito e soglie restano in `esito()`.
- La bacheca (ricevuta → scheda interpretata) e la sua impronta SHA-256 si
  pubblicano a votazione chiusa; l'impronta va nel verbale."""

from __future__ import annotations

import hashlib
import random
import uuid
from collections import Counter
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente
from apps.assemblee.models import AventeDiritto, Candidato, Votazione
from apps.assemblee.permessi import puo_operare

from . import urna
from .models import InterpretazioneNome, Scheda, Votante


def _verifica_operatore(utente: Utente, votazione: Votazione) -> None:
    if not puo_operare(utente, votazione.seduta.assemblea):
        raise PermissionDenied


def chiave_nome(testo: str) -> str:
    return " ".join(testo.split()).casefold()


def urna_usata(votazione: Votazione) -> bool:
    return votazione.aperta_in_app_il is not None


def numero_votanti(votazione: Votazione) -> int:
    return Votante.objects.filter(votazione=votazione).count()


@transaction.atomic
def apri_urna(votazione: Votazione, utente: Utente) -> None:
    _verifica_operatore(utente, votazione)
    seduta = votazione.seduta
    if not seduta.assemblea.voto_catello:
        raise ValidationError("Questa assemblea non usa il voto in app.")
    if not urna.votazioni_in_app(votazione):
        raise ValidationError("Questa votazione non si vota in app.")
    if not seduta.aperta or seduta.costituita is not True:
        raise ValidationError("Si vota solo in una seduta costituita e aperta.")
    if votazione.chiusa or urna_usata(votazione):
        raise ValidationError("L'urna di questa votazione è già stata aperta.")
    altra = urna.votazione_aperta(seduta)
    if altra is not None:
        raise ValidationError(f"C'è già un'urna aperta: «{altra.oggetto}». Chiudila prima.")
    votazione.aperta_in_app_il = timezone.now()
    votazione.save(update_fields=["aperta_in_app_il"])


def _rimescola(votazione: Votazione) -> None:
    """Riscrive le schede in ordine casuale con id nuovi: nel dato a regime
    non resta traccia dell'ordine (né dello xmin) in cui sono state votate."""
    schede = list(Scheda.objects.filter(votazione=votazione).values("ricevuta", "scelte"))
    random.SystemRandom().shuffle(schede)
    Scheda.objects.filter(votazione=votazione).delete()
    Scheda.objects.bulk_create(
        Scheda(id=uuid.uuid4(), votazione=votazione, ricevuta=s["ricevuta"], scelte=s["scelte"])
        for s in schede
    )


@transaction.atomic
def chiudi_urna(votazione: Votazione, utente: Utente) -> None:
    _verifica_operatore(utente, votazione)
    # Lock sulla riga contro voti concorrenti, poi stato aggiornato sull'oggetto ricevuto.
    bloccata = Votazione.objects.select_for_update().get(pk=votazione.pk)
    votazione.aperta_in_app_il = bloccata.aperta_in_app_il
    votazione.chiusa_in_app_il = bloccata.chiusa_in_app_il
    votazione.chiusa_il = bloccata.chiusa_il
    if not votazione.urna_aperta:
        raise ValidationError("L'urna di questa votazione non è aperta.")
    schede = Scheda.objects.filter(votazione=votazione).count()
    votanti = numero_votanti(votazione)
    if schede != votanti:
        # Non deve accadere (schede e votanti nascono nella stessa
        # transazione): se accade l'urna non si chiude e va segnalato.
        raise ValidationError(
            f"Urna incoerente: {schede} schede per {votanti} votanti. Non chiudere: avvisa "
            "l'amministratore."
        )
    _rimescola(votazione)
    votazione.chiusa_in_app_il = timezone.now()
    votazione.save(update_fields=["chiusa_in_app_il"])


# --- Nomi scritti ---------------------------------------------------------------


@dataclass
class NomeDaInterpretare:
    chiave: str
    testo: str
    schede: int
    decisione: InterpretazioneNome | None = None


def nomi_scritti(votazione: Votazione) -> list[NomeDaInterpretare]:
    """Testi distinti scritti nelle schede, con quante schede li contengono e
    l'eventuale decisione già presa. Solo a urna chiusa."""
    if votazione.chiusa_in_app_il is None:
        return []
    conteggio: Counter[str] = Counter()
    testi: dict[str, str] = {}
    for scelte in Scheda.objects.filter(votazione=votazione).values_list("scelte", flat=True):
        if scelte.get("esito") != urna.ESITO_VOTO:
            continue
        for testo in scelte.get("liberi", []):
            chiave = chiave_nome(testo)
            conteggio[chiave] += 1
            testi.setdefault(chiave, " ".join(testo.split()))
    decisioni = {d.chiave: d for d in votazione.interpretazioni_nomi.select_related("avente")}
    return [
        NomeDaInterpretare(chiave, testi[chiave], conteggio[chiave], decisioni.get(chiave))
        for chiave in sorted(conteggio)
    ]


def nomi_da_interpretare(votazione: Votazione) -> list[NomeDaInterpretare]:
    return [n for n in nomi_scritti(votazione) if n.decisione is None]


@transaction.atomic
def interpreta(
    votazione: Votazione, testo: str, avente: AventeDiritto | None, utente: Utente
) -> InterpretazioneNome:
    """Decisione della commissione su un nome scritto: `avente` (a cui il nome
    si attribuisce) o None (nullo). Modificabile fino alla registrazione dei
    risultati."""
    _verifica_operatore(utente, votazione)
    if votazione.chiusa_in_app_il is None:
        raise ValidationError("I nomi scritti si interpretano a urna chiusa.")
    if votazione.chiusa:
        raise ValidationError("I risultati sono già registrati.")
    chiave = chiave_nome(testo)
    if chiave not in {n.chiave for n in nomi_scritti(votazione)}:
        raise ValidationError("Questo nome non compare nelle schede.")
    if avente is not None and (
        avente.assemblea_id != votazione.seduta.assemblea_id or avente.eliminato
    ):
        raise ValidationError("Si attribuisce solo a un avente diritto dell'assemblea.")
    decisione, _ = InterpretazioneNome.objects.update_or_create(
        votazione=votazione,
        chiave=chiave,
        defaults={
            "avente": avente,
            "decisa_da": utente,
            "decisa_il": timezone.now(),
        },
    )
    return decisione


def _candidato_per_avente(votazione: Votazione, avente: AventeDiritto) -> Candidato:
    """Il candidato collegato all'avente; se non c'è, lo si aggiunge (chi
    riceve voti come nome scritto diventa candidato, docs/plan_voto.md)."""
    candidato = votazione.candidati.filter(avente=avente).first()
    if candidato is None:
        candidato = Candidato.objects.create(
            votazione=votazione, avente=avente, nome=f"{avente.cognome} {avente.nome}"
        )
    return candidato


# --- Conteggio e bacheca ---------------------------------------------------------


@dataclass
class Conteggio:
    voti: dict[int, int] = field(default_factory=dict)
    bianche: int = 0
    nulle: int = 0
    schede: int = 0


def _scheda_interpretata(scelte: dict, attribuzioni: dict[str, int | None]) -> dict:
    """Scheda come la si conta e la si pubblica: candidati (id) validi dopo
    l'interpretazione dei nomi scritti. Una scheda di voto senza preferenze
    valide è nulla."""
    esito = scelte.get("esito")
    if esito != urna.ESITO_VOTO:
        return {"esito": esito, "candidati": []}
    candidati = list(dict.fromkeys(scelte.get("candidati", [])))
    for testo in scelte.get("liberi", []):
        candidato = attribuzioni.get(chiave_nome(testo))
        if candidato is not None and candidato not in candidati:
            candidati.append(candidato)
    if not candidati:
        return {"esito": urna.ESITO_NULLA, "candidati": []}
    return {"esito": urna.ESITO_VOTO, "candidati": sorted(candidati)}


def _attribuzioni(votazione: Votazione) -> dict[str, int | None]:
    risultato: dict[str, int | None] = {}
    for decisione in votazione.interpretazioni_nomi.select_related("avente"):
        if decisione.avente is None:
            risultato[decisione.chiave] = None
        else:
            risultato[decisione.chiave] = _candidato_per_avente(votazione, decisione.avente).pk
    return risultato


def conteggio(votazione: Votazione) -> Conteggio:
    """Voti in app per candidato, bianche e nulle. Solo a urna chiusa e con
    tutti i nomi scritti interpretati; aggiunge i candidati che servono."""
    risultato = Conteggio(voti={c.pk: 0 for c in votazione.candidati.all()})
    if not urna_usata(votazione):
        return risultato
    if votazione.chiusa_in_app_il is None:
        raise ValidationError("Chiudi l'urna elettronica prima di registrare i risultati.")
    if nomi_da_interpretare(votazione):
        raise ValidationError(
            "Ci sono nomi scritti ancora da interpretare: la commissione deve attribuirli o "
            "dichiararli nulli."
        )
    attribuzioni = _attribuzioni(votazione)
    risultato.voti = {c.pk: 0 for c in votazione.candidati.all()}
    for scheda in Scheda.objects.filter(votazione=votazione):
        interpretata = _scheda_interpretata(scheda.scelte, attribuzioni)
        risultato.schede += 1
        if interpretata["esito"] == urna.ESITO_BIANCA:
            risultato.bianche += 1
        elif interpretata["esito"] == urna.ESITO_NULLA:
            risultato.nulle += 1
        else:
            for candidato in interpretata["candidati"]:
                risultato.voti[candidato] = risultato.voti.get(candidato, 0) + 1
    return risultato


def _riga_bacheca(ricevuta: str, interpretata: dict, nomi: dict[int, str]) -> str:
    if interpretata["esito"] == urna.ESITO_BIANCA:
        return f"{ricevuta}: scheda bianca"
    if interpretata["esito"] == urna.ESITO_NULLA:
        return f"{ricevuta}: scheda nulla"
    return f"{ricevuta}: " + ", ".join(sorted(nomi[c] for c in interpretata["candidati"]))


def righe_bacheca(votazione: Votazione) -> list[str]:
    """Una riga per scheda, in ordine di ricevuta: deterministica, quindi
    l'impronta si ricalcola uguale."""
    per_avente = dict(
        votazione.candidati.filter(avente__isnull=False).values_list("avente_id", "pk")
    )
    attribuzioni = {
        d.chiave: None if d.avente_id is None else per_avente.get(d.avente_id)
        for d in votazione.interpretazioni_nomi.all()
    }
    nomi = dict(votazione.candidati.values_list("pk", "nome"))
    return [
        _riga_bacheca(s.ricevuta, _scheda_interpretata(s.scelte, attribuzioni), nomi)
        for s in Scheda.objects.filter(votazione=votazione).order_by("ricevuta")
    ]


def impronta(righe: list[str]) -> str:
    return hashlib.sha256("\n".join(righe).encode("utf-8")).hexdigest()


def pubblica_bacheca(votazione: Votazione) -> None:
    """Chiamata da `registra_risultati()` a conteggio fatto: fissa l'impronta."""
    if not urna_usata(votazione):
        return
    votazione.hash_bacheca = impronta(righe_bacheca(votazione))
    votazione.save(update_fields=["hash_bacheca"])


@dataclass
class EsitoVerifica:
    trovata: bool
    pubblicata: bool = False
    votazione: Votazione | None = None
    riga: str = ""


def verifica_ricevuta(ricevuta: str) -> EsitoVerifica:
    """Prima della chiusura dice solo «scheda nell'urna»; a risultati
    registrati mostra la scheda come appare in bacheca."""
    from . import codici

    scheda = (
        Scheda.objects.filter(ricevuta=codici.formatta(ricevuta))
        .select_related("votazione")
        .first()
    )
    if scheda is None:
        return EsitoVerifica(trovata=False)
    votazione = scheda.votazione
    if not votazione.chiusa:
        return EsitoVerifica(trovata=True, votazione=votazione)
    riga = next((r for r in righe_bacheca(votazione) if r.startswith(f"{scheda.ricevuta}:")), "")
    return EsitoVerifica(trovata=True, pubblicata=True, votazione=votazione, riga=riga)


def nota_verbale(votazione: Votazione) -> str:
    """Frase per il verbale sul voto elettronico: numeri e impronta, mai i
    testi scritti dagli elettori."""
    if not urna_usata(votazione) or not votazione.hash_bacheca:
        return ""
    nomi = nomi_scritti(votazione)
    attribuiti = sum(n.schede for n in nomi if n.decisione and n.decisione.avente_id)
    nulli = sum(n.schede for n in nomi if n.decisione and n.decisione.avente_id is None)
    parti = [f"Voto elettronico: {Scheda.objects.filter(votazione=votazione).count()} schede"]
    if nomi:
        parti.append(
            f"nomi scritti interpretati dalla commissione elettorale: {attribuiti} attribuiti, "
            f"{nulli} nulli"
        )
    parti.append(f"impronta SHA-256 della bacheca {votazione.hash_bacheca}")
    return "; ".join(parti) + "."
