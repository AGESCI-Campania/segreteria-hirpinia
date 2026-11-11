"""Verbale dell'assemblea in PDF (D-70), sulla struttura del modello nazionale:
frasi fisse con i dati della seduta, un paragrafo per punto all'ordine del
giorno con la discussione e la frase di esito di ogni votazione collegata.
WeasyPrint importato in modo lazy, come negli altri PDF del progetto."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.template.loader import render_to_string

from apps.accounts.models import Utente
from apps.core.pdf import contesto_carta_intestata

from . import comitato, presidenza
from .models import (
    AventeDiritto,
    Seduta,
    TipoAppello,
    TipoVotazione,
    VariazioneRappresentante,
    VerbaleSeduta,
    Votazione,
)
from .permessi import puo_compilare_verbale, puo_gestire_assemblee
from .quorum import verifica_senza_quorum
from .votazioni import frase_esito, soglie_correnti


@dataclass(frozen=True)
class VotazioneVerbale:
    votazione: Votazione
    frase: str
    # Voto elettronico di Catello: schede in app e impronta della bacheca.
    nota_app: str = ""


def _votazioni(qs) -> list[VotazioneVerbale]:
    # Lazy: apps.voto dipende da questo modulo, non il contrario.
    from apps.voto.scrutinio import nota_verbale

    return [VotazioneVerbale(v, frase_esito(v), nota_verbale(v)) for v in qs.order_by("aperta_il")]


def verbale_della_seduta(seduta: Seduta) -> VerbaleSeduta:
    """Il verbale della seduta, creato la prima volta che serve con il luogo
    della seduta e l'ufficio di presidenza indicato in preparazione (D7)."""
    verbale, _ = VerbaleSeduta.objects.get_or_create(
        seduta=seduta,
        defaults={"luogo": seduta.luogo, **presidenza.dati_per_verbale(seduta.assemblea)},
    )
    return verbale


def riprendi_dalla_preparazione(seduta: Seduta, utente: Utente) -> None:
    """Riporta nel verbale presidenza, segretario, comitato mozioni e
    scrutatori come sono ora nella preparazione dell'assemblea."""
    if not puo_compilare_verbale(utente, seduta.assemblea):
        raise PermissionDenied
    verbale = verbale_della_seduta(seduta)
    dati = presidenza.dati_per_verbale(seduta.assemblea)
    for campo, valore in dati.items():
        setattr(verbale, campo, valore)
    verbale.save(update_fields=[*dati, "aggiornato_il"])


def _membri_mozioni(testo: str) -> int:
    return len([n for n in testo.split(",") if n.strip()])


def contesto_verbale(seduta: Seduta) -> dict:
    if seduta.costituita is not True:
        raise ValidationError("Il verbale si redige per una seduta validamente costituita.")
    assemblea = seduta.assemblea
    chiuse = seduta.votazioni.filter(chiusa_il__isnull=False).select_related("punto")
    punti = [
        (punto, _votazioni(chiuse.filter(punto=punto)))
        for punto in assemblea.punti_odg.order_by("ordine")
    ]
    aventi = seduta.aventi_alla_costituzione or 0
    verifiche = [
        (verifica, soglie_correnti(verifica.presenti_rilevati or 0, aventi)["deliberazioni"])
        for verifica in seduta.appelli.filter(
            tipo=TipoAppello.VERIFICA, chiuso_il__isnull=False
        ).order_by("numero")
    ]
    mozioni = chiuse.filter(
        tipo__in=[TipoVotazione.MOZIONE, TipoVotazione.RACCOMANDAZIONE]
    ).exists()
    return {
        "assemblea": assemblea,
        "seduta": seduta,
        "verbale": verbale_della_seduta(seduta),
        "punti": punti,
        "senza_punto": _votazioni(chiuse.filter(punto__isnull=True)),
        "verifiche": verifiche,
        "verifica_senza_quorum": verifica_senza_quorum(seduta),
        "ci_sono_mozioni": mozioni,
        "comitato_elettorale": [c.nome_completo for c in comitato.componenti(assemblea)],
        # Il comitato mozioni è sempre di tre (D10): i mancanti in rosso.
        "mozioni_mancanti": range(
            max(0, 3 - _membri_mozioni(verbale_della_seduta(seduta).comitato_mozioni))
        ),
        **contesto_carta_intestata(),
    }


def genera_verbale_pdf(seduta: Seduta, utente: Utente) -> bytes:
    from weasyprint import HTML

    if not puo_compilare_verbale(utente, seduta.assemblea):
        raise PermissionDenied
    html = render_to_string("assemblee/verbale_pdf.html", contesto_verbale(seduta))
    return HTML(string=html).write_pdf()


# --- Variazione della rappresentanza legale ------------------------------------------


def variazione_della_seduta(seduta: Seduta) -> VariazioneRappresentante:
    variazione, _ = VariazioneRappresentante.objects.get_or_create(seduta=seduta)
    return variazione


def precompila_rappresentante(
    variazione: VariazioneRappresentante, avente: AventeDiritto, utente: Utente
) -> None:
    """Copia nei campi del verbale i dati anagrafici del Responsabile di Zona
    scelto. Il rappresentante si nomina fra i Responsabili di Zona (art. 24
    dello Statuto). La provincia di nascita non è in anagrafica: resta da
    scrivere a mano."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if avente.assemblea_id != variazione.seduta.assemblea_id or not avente.rdz:
        raise ValidationError("Il rappresentante legale si sceglie fra i Responsabili di Zona.")
    variazione.rappresentante = avente
    variazione.cognome = avente.cognome
    variazione.nome = avente.nome
    capo = avente.capo
    if capo is not None:
        variazione.codice_fiscale = capo.codice_fiscale
        variazione.comune_nascita = capo.comune_nascita
        variazione.data_nascita = capo.data_nascita
        variazione.indirizzo = capo.indirizzo
        variazione.civico = capo.civico
        variazione.cap = capo.cap
        variazione.comune_residenza = capo.comune_residenza
        variazione.provincia_residenza = capo.provincia_residenza
    variazione.save()


def genera_variazione_pdf(seduta: Seduta, utente: Utente) -> bytes:
    from weasyprint import HTML

    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if seduta.costituita is not True:
        raise ValidationError("Il verbale si redige per una seduta validamente costituita.")
    contesto = {
        "assemblea": seduta.assemblea,
        "seduta": seduta,
        "verbale": verbale_della_seduta(seduta),
        "variazione": variazione_della_seduta(seduta),
        **contesto_carta_intestata(),
    }
    html = render_to_string("assemblee/variazione_rappresentante_pdf.html", contesto)
    return HTML(string=html).write_pdf()
