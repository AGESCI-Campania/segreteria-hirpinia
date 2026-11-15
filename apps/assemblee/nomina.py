"""Email di nomina per chi opera durante l'assemblea: componenti del comitato
elettorale, presidenti, segretario e scrutatori (il comitato mozioni no, non
opera sulla piattaforma). Parte a ogni nomina, anche a chi ha già un account o
non ha l'accesso, all'email dell'elenco, con i link ai manuali giusti per
l'incarico su Read the Docs (versione stable, l'ultima release). L'invito di
attivazione dell'account, se serve, resta un'email a parte (comitato.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse

from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail

from . import prova
from .models import Assemblea, AventeDiritto, RuoloAssemblea

logger = logging.getLogger(__name__)

ETICHETTA_NOMINA = "nomina"

# Il comitato elettorale non è un RuoloAssemblea (è OperatoreVoto).
COMITATO_ELETTORALE = "COMITATO_ELETTORALE"


@dataclass(frozen=True)
class Manuale:
    titolo: str
    cartella: str
    pdf: str


GESTIONE = Manuale("Manuale di gestione dell'assemblea", "gestione", "manuale-gestione.pdf")
BANCO = Manuale("Manuale per il banco e i seggi", "banco", "manuale-banco.pdf")
VOTO_APP = Manuale("Manuale di voto in app", "voto-app", "manuale-voto-app.pdf")
VOTO_SEGGIO = Manuale("Manuale di voto al seggio", "voto-seggio", "manuale-voto-seggio.pdf")

# Incarico → (nome nell'email, manuali per chi opera).
INCARICHI: dict[str, tuple[str, tuple[Manuale, ...]]] = {
    COMITATO_ELETTORALE: ("componente del comitato elettorale", (BANCO, GESTIONE)),
    RuoloAssemblea.SCRUTATORE: ("scrutatore", (BANCO, GESTIONE)),
    RuoloAssemblea.PRESIDENTE: ("presidente", (GESTIONE,)),
    RuoloAssemblea.SEGRETARIO: ("segretario", (GESTIONE,)),
}


def _riga(manuale: Manuale) -> str:
    base = settings.MANUALI_ASSEMBLEA_URL.rstrip("/")
    return (
        f"- {manuale.titolo}:\n  {base}/{manuale.cartella}/\n"
        f"  PDF: {base}/{manuale.cartella}/pdf/{manuale.pdf}"
    )


def testo_manuali(incarico: str) -> str:
    """Il blocco `{{ manuali }}`: i manuali per l'incarico, poi quelli di voto
    da girare ai votanti."""
    _, propri = INCARICHI[incarico]
    return (
        "\n".join(_riga(m) for m in propri)
        + "\n\nPer i votanti, se ti chiedono come si vota:\n"
        + "\n".join(_riga(m) for m in (VOTO_APP, VOTO_SEGGIO))
    )


def contesto(assemblea: Assemblea, avente: AventeDiritto, incarico: str) -> dict[str, str]:
    descrizione, _ = INCARICHI[incarico]
    prima = assemblea.sedute.order_by("convocazione").first()
    return {
        "nome": avente.nome,
        "assemblea": str(assemblea),
        "incarico": descrizione,
        "data": f"{prima.data:%d/%m/%Y}" if prima else "",
        "manuali": testo_manuali(incarico),
        "link": f"{settings.SITE_URL}{reverse('assemblee:assemblea_dettaglio', args=[assemblea.pk])}",
    }


def invia(assemblea: Assemblea, avente: AventeDiritto, incarico: str) -> bool | None:
    """Invia l'email di nomina. Restituisce None se non c'è nulla da inviare
    (incarico senza email di nomina o capo senza email), False se l'invio è
    fallito: la nomina resta comunque valida."""
    if incarico not in INCARICHI or not avente.email:
        return None
    try:
        invia_email_template(
            codice_template=CodiceTemplateEmail.NOMINA_ASSEMBLEA,
            destinatari=[avente.email],
            contesto=contesto(assemblea, avente, incarico),
            fail_silently=False,
            **prova.opzioni_invio(assemblea, ETICHETTA_NOMINA),
        )
    except Exception:
        logger.exception(
            "Invio dell'email di nomina per un'assemblea non riuscito (1 destinatario)"
        )
        return False
    return True
