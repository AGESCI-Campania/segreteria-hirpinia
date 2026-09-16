"""Transizioni della macchina a stati (D-37/D-38/D-39/D-40). Permessi ed
effetti collaterali vivono qui, mai nei metodi `@transition` del modello
(D-69, service layer condiviso — pattern già in uso in
`apps/contributi/campagne.py` per `Campagna`)."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente

from .anno_associativo import calcola_anno_spesa
from .budget import capienza_centro_costo
from .models import (
    AutorizzazioneRdz,
    AutorizzazioneRdzConfig,
    CentroCosto,
    GenereRdz,
    ImpostazioniNoteSpese,
    NotaSpese,
    RigaSpesa,
    StatoNota,
)
from .permessi import (
    e_beneficiario_della_nota,
    e_compilatore_della_nota,
    genere_rdz,
    puo_autorizzare_rdz,
    puo_gestire_note,
)

logger = logging.getLogger(__name__)


def _richiedi_permesso_capo(utente: Utente, nota: NotaSpese) -> None:
    """D-36: oltre al beneficiario, autorizzato anche il compilatore per
    conto terzi (segreteria/RdZ/admin che ha compilato la nota per un altro
    capo) — sta al posto del beneficiario per l'intero ciclo di vita lato
    capo (invio, conferme, annullamento), non solo per la creazione."""
    if not (e_beneficiario_della_nota(utente, nota) or e_compilatore_della_nota(utente, nota)):
        raise PermissionDenied(
            "Solo il beneficiario o chi ha compilato la nota per suo conto (D-36) può "
            "compiere questa azione."
        )


def _richiedi_permesso_gestione(utente: Utente) -> None:
    if not puo_gestire_note(utente):
        raise PermissionDenied("Serve un ruolo di segreteria, RdZ o admin per questa azione.")


def _genera_numero(anno_spesa: int) -> str:
    prefisso = f"{anno_spesa}/"
    ultima = NotaSpese.objects.filter(numero__startswith=prefisso).order_by("-numero").first()
    progressivo = int(ultima.numero.split("/")[1]) + 1 if ultima and ultima.numero else 1
    return f"{prefisso}{progressivo:04d}"


@transaction.atomic
def invia_nota(nota: NotaSpese, utente: Utente) -> NotaSpese:
    """BOZZA -> INVIATA. Assegna `numero`/`anno_spesa` qui, non alla
    creazione (vedi trappola documentata su `NotaSpese`, dedotta perché
    `anno_spesa` non è derivabile da una nota ancora senza righe)."""
    _richiedi_permesso_capo(utente, nota)
    date_righe = list(nota.righe.values_list("data", flat=True))
    if not date_righe:
        raise ValidationError("Una nota senza righe di spesa non può essere inviata.")
    anno_spesa = calcola_anno_spesa(date_righe)
    assert anno_spesa is not None  # date_righe non è vuoto, verificato sopra
    nota.anno_spesa = anno_spesa
    nota.numero = _genera_numero(anno_spesa)
    nota.invia()
    nota.save()
    return nota


@transaction.atomic
def prendi_in_carico(nota: NotaSpese, utente: Utente) -> NotaSpese:
    _richiedi_permesso_gestione(utente)
    nota.prendi_in_carico()
    nota.save()
    return nota


@transaction.atomic
def richiedi_integrazione(
    nota: NotaSpese, utente: Utente, riga: RigaSpesa, testo: str
) -> NotaSpese:
    """D-38: si sblocca **solo** con un nuovo allegato sulla riga."""
    _richiedi_permesso_gestione(utente)
    if riga.nota_id != nota.pk:
        raise ValidationError("La riga indicata non appartiene a questa nota.")
    nota.rilievo_riga = riga
    nota.rilievo_nota = testo
    nota.rilievo_il = timezone.now()
    nota.richiedi_integrazione()
    nota.save()
    return nota


@transaction.atomic
def richiedi_conferma(nota: NotaSpese, utente: Utente, riga: RigaSpesa, testo: str) -> NotaSpese:
    """D-38: si sblocca con un semplice assenso del capo, nessun allegato."""
    _richiedi_permesso_gestione(utente)
    if riga.nota_id != nota.pk:
        raise ValidationError("La riga indicata non appartiene a questa nota.")
    nota.rilievo_riga = riga
    nota.rilievo_nota = testo
    nota.rilievo_il = timezone.now()
    nota.richiedi_conferma()
    nota.save()
    return nota


@transaction.atomic
def conferma_integrazione(nota: NotaSpese, utente: Utente) -> NotaSpese:
    """D-38: la condizione di sblocco si verifica qui, non lasciata
    all'interfaccia — un nuovo allegato caricato dopo il rilievo, sulla
    riga oggetto del rilievo."""
    _richiedi_permesso_capo(utente, nota)
    riga_segnalata = nota.rilievo_riga
    if riga_segnalata is None or nota.rilievo_il is None:
        raise ValidationError("Nessun rilievo da sbloccare su questa nota.")
    ha_nuovo_allegato = riga_segnalata.allegati.filter(caricato_il__gt=nota.rilievo_il).exists()
    if not ha_nuovo_allegato:
        raise ValidationError(
            "Serve un nuovo allegato sulla riga segnalata prima di poter proseguire (D-38)."
        )
    nota.conferma_integrazione()
    nota.save()
    return nota


@transaction.atomic
def conferma_correzione(nota: NotaSpese, utente: Utente) -> NotaSpese:
    """D-38: si sblocca con un semplice assenso, nessun controllo su allegati."""
    _richiedi_permesso_capo(utente, nota)
    nota.conferma_correzione()
    nota.save()
    return nota


@transaction.atomic
def correggi_importo_riga(riga: RigaSpesa, nuovo_importo: Decimal, utente: Utente) -> RigaSpesa:
    """D-39: congela `importo_originale` alla **prima** correzione dopo
    l'invio, mai più sovrascritto (decisione presa con Andrea: solo il
    campo importo, non un meccanismo generico)."""
    _richiedi_permesso_gestione(utente)
    if riga.importo_originale is None and riga.importo is not None:
        riga.importo_originale = riga.importo
    riga.importo = nuovo_importo
    riga.save()
    return riga


@transaction.atomic
def imputa_centro_costo(nota: NotaSpese, utente: Utente, centro_costo: CentroCosto) -> NotaSpese:
    """D-44: l'imputazione è riservata a segreteria/RdZ/admin, mai al
    beneficiario o al compilatore. Non è una transizione FSM (nessun campo
    di stato coinvolto). **Inferenza dichiarata**: i requisiti non
    specificano un vincolo di stato esplicito; blocco solo dopo `LIQUIDATA`
    perché a quel punto il consumo del budget (D-47/D-48) è già calcolato
    sul nodo precedente e cambiarlo lo renderebbe incoerente col passato."""
    _richiedi_permesso_gestione(utente)
    if nota.stato == StatoNota.LIQUIDATA:
        raise ValidationError("Non si può cambiare il centro di costo di una nota già liquidata.")
    nota.centro_costo = centro_costo
    nota.save()
    return nota


@transaction.atomic
def approva(nota: NotaSpese, utente: Utente) -> NotaSpese:
    _richiedi_permesso_gestione(utente)
    nota.approva()
    nota.save()
    return nota


@transaction.atomic
def autorizza_rdz(nota: NotaSpese, utente: Utente) -> NotaSpese:
    """D-35: SINGOLA basta una firma di un RdZ qualsiasi; DOPPIA richiede una
    firma maschile e una femminile (vincolo di genere, non di conteggio).

    **Inferenza dichiarata**: Admin bypassa il quorum (nessuna riga
    `AutorizzazioneRdz` creata), dedotto da "Admin: nessun vincolo" in §2
    — non testato esplicitamente contro D-35, che parla solo di RdZ."""
    if not puo_autorizzare_rdz(utente):
        raise PermissionDenied("Serve un ruolo di RdZ o admin per autorizzare.")
    config = ImpostazioniNoteSpese.corrente().autorizzazione_rdz
    if config == AutorizzazioneRdzConfig.NESSUNA:
        raise ValidationError("L'autorizzazione RdZ non è attiva per questa configurazione.")

    if utente.is_superuser:
        nota.autorizza_rdz()
        nota.save()
        return nota

    genere = genere_rdz(utente)
    if genere is None:
        raise ValidationError(
            "L'account non corrisponde a nessuna delle caselle di funzione RdZ configurate."
        )
    AutorizzazioneRdz.objects.get_or_create(nota=nota, genere=genere, defaults={"utente": utente})

    firme = set(nota.autorizzazioni_rdz.values_list("genere", flat=True))
    if config == AutorizzazioneRdzConfig.SINGOLA:
        pronta = bool(firme)
    else:  # DOPPIA
        pronta = {GenereRdz.MASCHILE, GenereRdz.FEMMINILE}.issubset(firme)

    if not pronta:
        return nota  # Firma registrata, ma la transizione scatta solo a quorum raggiunto.

    nota.autorizza_rdz()
    nota.save()
    return nota


@transaction.atomic
def liquida(nota: NotaSpese, utente: Utente, *, anno_liquidazione: int) -> NotaSpese:
    """D-40: transizione terminale. D-41: unico punto che valorizza
    `anno_contabilizzazione` — mai altrove. D-47/D-48: qui si consuma il
    budget del centro di costo imputato (mai un errore bloccante se
    sforato, solo un log — deciso con Andrea, 2026-09-16)."""
    _richiedi_permesso_gestione(utente)
    config = ImpostazioniNoteSpese.corrente().autorizzazione_rdz
    if config != AutorizzazioneRdzConfig.NESSUNA and nota.stato != StatoNota.AUTORIZZATA_RDZ:
        raise ValidationError(
            "La nota deve prima ricevere l'autorizzazione RdZ configurata (D-35)."
        )
    nota.anno_contabilizzazione = anno_liquidazione
    nota.liquida()
    nota.save()

    centro_costo = nota.centro_costo
    if centro_costo is not None:
        capienza = capienza_centro_costo(centro_costo, anno_liquidazione)
        if capienza.residuo < 0:
            logger.warning(
                "Nota %s liquidata sfora il budget del centro di costo %s per l'anno "
                "%s: residuo %s (D-47, non bloccante).",
                nota.numero,
                nota.centro_costo_id,
                anno_liquidazione,
                capienza.residuo,
            )

    return nota


@transaction.atomic
def respingi(nota: NotaSpese, utente: Utente, causale: str) -> NotaSpese:
    _richiedi_permesso_gestione(utente)
    if not causale.strip():
        raise ValidationError("Un respingimento richiede sempre una causale.")
    nota.causale_respinta = causale
    nota.respingi()
    nota.save()
    return nota


@transaction.atomic
def annulla(nota: NotaSpese, utente: Utente) -> NotaSpese:
    _richiedi_permesso_capo(utente, nota)
    nota.annulla()
    nota.save()
    return nota
