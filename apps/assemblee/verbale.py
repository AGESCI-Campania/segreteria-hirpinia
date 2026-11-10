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

from .models import (
    Seduta,
    TipoAppello,
    TipoVotazione,
    VerbaleSeduta,
    Votazione,
)
from .permessi import puo_gestire_assemblee
from .votazioni import frase_esito


@dataclass(frozen=True)
class VotazioneVerbale:
    votazione: Votazione
    frase: str


def _votazioni(qs) -> list[VotazioneVerbale]:
    return [VotazioneVerbale(v, frase_esito(v)) for v in qs.order_by("aperta_il")]


def verbale_della_seduta(seduta: Seduta) -> VerbaleSeduta:
    """Il verbale della seduta, creato vuoto (con il luogo della seduta) la
    prima volta che serve."""
    verbale, _ = VerbaleSeduta.objects.get_or_create(
        seduta=seduta, defaults={"luogo": seduta.luogo}
    )
    return verbale


def contesto_verbale(seduta: Seduta) -> dict:
    if seduta.costituita is not True:
        raise ValidationError("Il verbale si redige per una seduta validamente costituita.")
    assemblea = seduta.assemblea
    chiuse = seduta.votazioni.filter(chiusa_il__isnull=False).select_related("punto")
    punti = [
        (punto, _votazioni(chiuse.filter(punto=punto)))
        for punto in assemblea.punti_odg.order_by("ordine")
    ]
    verifiche = seduta.appelli.filter(tipo=TipoAppello.VERIFICA, chiuso_il__isnull=False)
    mozioni = chiuse.filter(
        tipo__in=[TipoVotazione.MOZIONE, TipoVotazione.RACCOMANDAZIONE]
    ).exists()
    return {
        "assemblea": assemblea,
        "seduta": seduta,
        "verbale": verbale_della_seduta(seduta),
        "punti": punti,
        "senza_punto": _votazioni(chiuse.filter(punto__isnull=True)),
        "verifiche": verifiche.order_by("numero"),
        "ci_sono_mozioni": mozioni,
        **contesto_carta_intestata(),
    }


def genera_verbale_pdf(seduta: Seduta, utente: Utente) -> bytes:
    from weasyprint import HTML

    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    html = render_to_string("assemblee/verbale_pdf.html", contesto_verbale(seduta))
    return HTML(string=html).write_pdf()
