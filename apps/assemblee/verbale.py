"""Verbale dell'assemblea in PDF (D-70), sulla struttura del modello nazionale:
frasi fisse con i dati della seduta, un paragrafo per punto all'ordine del
giorno con la discussione e la frase di esito di ogni votazione collegata.
WeasyPrint importato in modo lazy, come negli altri PDF del progetto."""

from __future__ import annotations

from dataclasses import dataclass

import bleach
from django.core.exceptions import PermissionDenied, ValidationError
from django.template.loader import render_to_string
from django.utils.html import linebreaks

from apps.accounts.models import Utente
from apps.core.pdf import contesto_carta_intestata

from . import comitato, presidenza
from .models import (
    AventeDiritto,
    Seduta,
    Sesso,
    TipoAppello,
    TipoVotazione,
    VariazioneRappresentante,
    VerbaleSeduta,
    Votazione,
)
from .permessi import puo_compilare_verbale, puo_gestire_assemblee
from .quorum import verifica_senza_quorum
from .votazioni import esito, frase_esito, soglie_correnti


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
        defaults={"luogo": seduta.luogo, **_dati_preparazione(seduta)},
    )
    return verbale


def rdz_in_carica(seduta: Seduta) -> dict[str, str]:
    """I Responsabili di Zona in carica all'inizio dell'assemblea, dalla
    qualifica nell'elenco degli aventi diritto, uno per sesso (sesso
    dell'elenco). Con più RdZ dello stesso sesso, o senza sesso noto, quel
    posto resta da scrivere a mano: niente scelte indovinate."""
    rdz = list(seduta.assemblea.aventi_diritto.nell_elenco().filter(rdz=True))
    dati = {}
    for campo, sesso in (("rdz_femminile", Sesso.FEMMINILE), ("rdz_maschile", Sesso.MASCHILE)):
        trovati = [a for a in rdz if a.sesso == sesso]
        dati[campo] = f"{trovati[0].cognome} {trovati[0].nome}" if len(trovati) == 1 else ""
    return dati


def _dati_preparazione(seduta: Seduta) -> dict[str, str]:
    return {**presidenza.dati_per_verbale(seduta.assemblea), **rdz_in_carica(seduta)}


def riprendi_dalla_preparazione(seduta: Seduta, utente: Utente) -> None:
    """Riporta nel verbale presidenza, segretario, comitato mozioni e
    scrutatori come sono ora nella preparazione dell'assemblea, e i
    Responsabili di Zona in carica dall'elenco."""
    if not puo_compilare_verbale(utente, seduta.assemblea):
        raise PermissionDenied
    verbale = verbale_della_seduta(seduta)
    dati = _dati_preparazione(seduta)
    for campo, valore in dati.items():
        setattr(verbale, campo, valore)
    verbale.save(update_fields=[*dati, "aggiornato_il"])


# Note finali del verbale: testo formattato dall'editor (TinyMCE senza
# immagini), con un vocabolario minimo. `strip=True` toglie i tag non ammessi.
TAG_NOTE_FINALI = ["p", "br", "strong", "em", "u", "ul", "ol", "li"]


def sanifica_note_finali(html: str) -> str:
    return bleach.clean(html, tags=TAG_NOTE_FINALI, attributes={}, protocols=[], strip=True)


def note_finali_html(testo: str) -> str:
    """Le note finali come HTML sicuro. Quelle scritte prima dell'editor sono
    testo semplice: gli a capo diventano paragrafi, il resto si fa escape."""
    if not testo.strip():
        return ""
    if testo.lstrip().startswith("<"):
        return sanifica_note_finali(testo)
    return linebreaks(testo, autoescape=True)


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
    verbale = verbale_della_seduta(seduta)
    return {
        "assemblea": assemblea,
        "seduta": seduta,
        "verbale": verbale,
        "note_finali": note_finali_html(verbale.note_finali),
        "punti": punti,
        "senza_punto": _votazioni(chiuse.filter(punto__isnull=True)),
        "verifiche": verifiche,
        "verifica_senza_quorum": verifica_senza_quorum(seduta),
        "ci_sono_mozioni": mozioni,
        "comitato_elettorale": [c.nome_completo for c in comitato.componenti(assemblea)],
        # Il comitato mozioni è sempre di tre (D10): i mancanti in rosso.
        "mozioni_mancanti": range(max(0, 3 - _membri_mozioni(verbale.comitato_mozioni))),
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


@dataclass(frozen=True)
class SceltaRappresentante:
    avente: AventeDiritto
    # Per gli eletti nella seduta: l'incarico per cui sono stati eletti.
    nota: str = ""


def scelte_rappresentante(seduta: Seduta) -> list[tuple[str, list[SceltaRappresentante]]]:
    """Fra chi scegliere il rappresentante legale, a gruppi: prima gli eletti
    nelle elezioni chiuse della seduta (secondo `esito()`), poi i Responsabili
    di Zona dell'elenco, poi tutti gli altri aventi diritto. La qualifica di
    RdZ nell'elenco è quella di prima dell'assemblea: chi viene eletto RdZ in
    seduta non ce l'ha ancora, quindi la scelta resta su tutto l'elenco."""
    nell_elenco = seduta.assemblea.aventi_diritto.nell_elenco().order_by("cognome", "nome")
    visti: set[int] = set()
    eletti: list[SceltaRappresentante] = []
    elezioni = seduta.votazioni.filter(
        chiusa_il__isnull=False, tipo__in=(TipoVotazione.ELEZIONE, TipoVotazione.BALLOTTAGGIO)
    ).order_by("aperta_il")
    for votazione in elezioni:
        for candidato in esito(votazione).eletti:
            avente = candidato.avente
            if avente is None or avente.eliminato_il is not None or avente.pk in visti:
                continue
            visti.add(avente.pk)
            eletti.append(SceltaRappresentante(avente, votazione.incarico or votazione.oggetto))
    rdz = [SceltaRappresentante(a) for a in nell_elenco.filter(rdz=True) if a.pk not in visti]
    visti.update(s.avente.pk for s in rdz)
    altri = [SceltaRappresentante(a) for a in nell_elenco if a.pk not in visti]
    gruppi = [
        ("Eletti in questa seduta", eletti),
        ("Responsabili di Zona", rdz),
        ("Altri aventi diritto", altri),
    ]
    return [(titolo, scelte) for titolo, scelte in gruppi if scelte]


def precompila_rappresentante(
    variazione: VariazioneRappresentante, avente: AventeDiritto, utente: Utente
) -> None:
    """Copia nei campi del verbale i dati anagrafici del Responsabile di Zona
    scelto (art. 24 dello Statuto), che può essere appena eletto e quindi non
    avere ancora la qualifica nell'elenco: si sceglie fra tutti gli aventi
    diritto (`scelte_rappresentante()`). La provincia di nascita non è in
    anagrafica: resta da scrivere a mano."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if avente.assemblea_id != variazione.seduta.assemblea_id or avente.eliminato_il is not None:
        raise ValidationError("Il rappresentante legale si sceglie fra gli aventi diritto.")
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
