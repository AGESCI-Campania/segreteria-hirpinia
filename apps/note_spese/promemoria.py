"""Promemoria al capo (D-63, F7): settimanale di norma, giornaliero negli
ultimi 15 giorni prima della chiusura dell'anno associativo (30 settembre,
`anno_associativo.py`). Nessuno scheduler: `invia_promemoria()` va chiamata
una volta al giorno da un processo esterno (comando di management
`note_spese_promemoria`, invocato da un loop nel container di produzione —
stesso pattern già in uso per `pulizia-sessioni` in `compose.prod.yaml`).
Decisione presa con Andrea il 2026-09-24, **non** Celery/Redis: D-17 in
CLAUDE.md resta valido così com'è."""

from __future__ import annotations

import datetime

from django.conf import settings
from django.urls import reverse

from apps.anagrafica.models import Capo
from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail

from .models import NotaSpese, StatoNota

# D-63: solo le note che richiedono un'azione del capo — una nota
# IN_VERIFICA non dipende da lui e non genera promemoria.
STATI_CHE_RICHIEDONO_AZIONE_CAPO = (
    StatoNota.BOZZA,
    StatoNota.DA_INTEGRARE,
    StatoNota.DA_CONFERMARE,
)

# Lunedì (decisione presa con Andrea, 2026-09-24): date.weekday() → 0=lunedì.
GIORNO_SETTIMANALE = 0
MESE_CHIUSURA_ANNO_ASSOCIATIVO = 9
GIORNO_CHIUSURA_ANNO_ASSOCIATIVO = 30
GIORNI_PRIMA_CHIUSURA_PER_GIORNALIERO = 15


def _giorni_alla_chiusura(data: datetime.date) -> int:
    chiusura = datetime.date(
        data.year, MESE_CHIUSURA_ANNO_ASSOCIATIVO, GIORNO_CHIUSURA_ANNO_ASSOCIATIVO
    )
    return (chiusura - data).days


def e_giorno_di_promemoria(data: datetime.date) -> bool:
    """D-63: giornaliero negli ultimi 15 giorni prima della chiusura
    (16-30 settembre inclusi), altrimenti solo il lunedì. Non gestisce
    il caso "oggi è dopo il 30 settembre di quest'anno civile": quella
    finestra ricade nell'anno associativo successivo, che chiude il 30
    settembre dell'anno civile successivo — `_giorni_alla_chiusura` la
    vedrebbe come "negativa" rispetto alla chiusura di quest'anno civile,
    ma a quel punto `data.weekday() == GIORNO_SETTIMANALE` prende comunque
    il sopravvento in autunno/inverno/primavera, dove serve solo il
    promemoria settimanale."""
    giorni_alla_chiusura = _giorni_alla_chiusura(data)
    if 0 <= giorni_alla_chiusura <= GIORNI_PRIMA_CHIUSURA_PER_GIORNALIERO:
        return True
    return data.weekday() == GIORNO_SETTIMANALE


def _elenco_note(note: list[NotaSpese]) -> tuple[str, str]:
    righe_testo = []
    righe_html = []
    for nota in note:
        numero = nota.numero or "(bozza)"
        riga = f"{numero} ({nota.evento}) — {nota.get_stato_display()}"
        righe_testo.append(f"- {riga}")
        righe_html.append(f"<li>{riga}</li>")
    return "\n".join(righe_testo), f"<ul>{''.join(righe_html)}</ul>"


def invia_promemoria(data: datetime.date | None = None) -> int:
    """Un'unica email digest per capo, non una per nota: inferenza
    dichiarata, D-63 non specifica la granularità e una per nota
    rischierebbe di sommergere chi ha più note in sospeso. Restituisce il
    numero di email effettivamente inviate (0 se oggi non è un giorno di
    promemoria, o se nessun beneficiario in sospeso ha un'email censita)."""
    data = data or datetime.date.today()
    if not e_giorno_di_promemoria(data):
        return 0

    note = (
        NotaSpese.objects.filter(
            stato__in=STATI_CHE_RICHIEDONO_AZIONE_CAPO, eliminata_il__isnull=True
        )
        .select_related("beneficiario", "evento")
        .order_by("beneficiario_id", "-creata_il")
    )

    per_capo: dict[str, list[NotaSpese]] = {}
    for nota in note:
        per_capo.setdefault(nota.beneficiario_id, []).append(nota)

    link = f"{settings.SITE_URL}{reverse('note_spese:nota_lista')}"
    inviate = 0
    for note_capo in per_capo.values():
        beneficiario: Capo = note_capo[0].beneficiario
        if not beneficiario.email:
            continue
        elenco, elenco_html = _elenco_note(note_capo)
        invia_email_template(
            codice_template=CodiceTemplateEmail.NOTA_SPESE_PROMEMORIA,
            destinatari=[beneficiario.email],
            contesto={"elenco": elenco, "elenco_html": elenco_html, "link": link},
        )
        inviate += 1
    return inviate
