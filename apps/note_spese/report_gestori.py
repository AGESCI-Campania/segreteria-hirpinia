"""Report periodico ai gestori (D-64, F7). Stesso approccio non-Celery di
D-63 (`promemoria.py`): valutato dal comando `note_spese_report_gestori`,
invocato da un loop esterno — mai da uno scheduler (D-17, deciso con
Andrea il 2026-09-24 di non introdurre Celery/Redis).

A differenza di D-63 (basta una volta al giorno), qui l'orario configurato
va rispettato: il loop deve poter girare più spesso di una volta al giorno,
quindi `invia_report_gestori()` si protegge da sé con
`ImpostazioniNoteSpese.report_ultimo_invio`, invece di affidarsi alla sola
cadenza del chiamante come fa `promemoria.py`."""

from __future__ import annotations

import datetime

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Ruolo
from apps.accounts.permessi import utenti_con_ruoli
from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail

from .models import ImpostazioniNoteSpese, NotaSpese, StatoNota

# D-64: quale campo booleano di ImpostazioniNoteSpese corrisponde a quale
# categoria di ruolo — "e loro delegati" è già coperto da
# utenti_con_ruoli() (diretto o per delega, D-28), non una quarta
# categoria a sé (decisione presa con Andrea il 2026-09-24).
RUOLI_PER_CAMPO_DESTINATARIO = {
    "report_destinatari_segreteria": Ruolo.Tipo.SEGRETERIA,
    "report_destinatari_rdz": Ruolo.Tipo.RDZ,
    "report_destinatari_admin": Ruolo.Tipo.ADMIN,
}


def destinatari_report(impostazioni: ImpostazioniNoteSpese) -> list[str]:
    tipi = [
        tipo for campo, tipo in RUOLI_PER_CAMPO_DESTINATARIO.items() if getattr(impostazioni, campo)
    ]
    if not tipi:
        return []
    return list(utenti_con_ruoli(tipi).exclude(email="").values_list("email", flat=True).distinct())


def _e_ora_di_inviare(impostazioni: ImpostazioniNoteSpese, adesso: datetime.datetime) -> bool:
    if not impostazioni.report_giorni_settimana or impostazioni.report_orario is None:
        return False
    if adesso.weekday() not in impostazioni.report_giorni_settimana:
        return False
    # ">=" e non "==": il loop non gira necessariamente esattamente
    # all'orario configurato, scatta al primo controllo utile dopo quel
    # momento. Il guardiano è report_ultimo_invio, non questo confronto.
    return adesso.time() >= impostazioni.report_orario


def _elenco_note(note: list[NotaSpese]) -> tuple[str, str]:
    righe_testo = []
    righe_html = []
    for nota in note:
        numero = nota.numero or "(bozza)"
        riga = f"{numero} ({nota.evento}) — {nota.beneficiario} — {nota.get_stato_display()}"
        righe_testo.append(f"- {riga}")
        righe_html.append(f"<li>{riga}</li>")
    return "\n".join(righe_testo), f"<ul>{''.join(righe_html)}</ul>"


@transaction.atomic
def invia_report_gestori(adesso: datetime.datetime | None = None) -> int:
    """D-64: contenuto = tutte le note non liquidate (lettura letterale del
    requisito: non ristretto agli stati "attivi", include anche
    respinte/annullate/decadute — se in uso si rivelasse troppo ampio, va
    rivisto esplicitamente, non ristretto per supposizione). Non inviato se
    non ci sono note in sospeso o se nessun destinatario è configurato.
    Restituisce il numero di email inviate. Un invio per destinatario, non
    un unico messaggio con più `to` (stesso pattern già in uso in
    `apps/anagrafica/incarichi.py::_notifica_incarico` e
    `apps/note_spese/transizioni.py::_notifica_capo`): i destinatari non
    devono vedersi a vicenda."""
    adesso = adesso or timezone.localtime()
    impostazioni = ImpostazioniNoteSpese.corrente()

    if impostazioni.report_ultimo_invio == adesso.date():
        return 0
    if not _e_ora_di_inviare(impostazioni, adesso):
        return 0

    destinatari = destinatari_report(impostazioni)
    if not destinatari:
        return 0

    note = list(
        NotaSpese.objects.exclude(stato=StatoNota.LIQUIDATA)
        .filter(eliminata_il__isnull=True)
        .select_related("beneficiario", "evento")
        .order_by("-creata_il")
    )
    if not note:
        return 0

    elenco, elenco_html = _elenco_note(note)
    contesto = {
        "elenco": elenco,
        "elenco_html": elenco_html,
        "numero_note": str(len(note)),
        "link": f"{settings.SITE_URL}{reverse('note_spese:nota_verifica_lista')}",
    }
    for email in destinatari:
        invia_email_template(
            codice_template=CodiceTemplateEmail.NOTA_SPESE_REPORT_GESTORI,
            destinatari=[email],
            contesto=contesto,
        )
    impostazioni.report_ultimo_invio = adesso.date()
    impostazioni.save(update_fields=["report_ultimo_invio"])
    return len(destinatari)
