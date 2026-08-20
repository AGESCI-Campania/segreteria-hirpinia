"""Sincronizzazione del ruolo CG con l'incarico di capogruppo (D-30). Vive in
`accounts` e non in `anagrafica` per evitare un import circolare:
`apps.anagrafica.importazione*` importa già `apps.accounts.models`, e questa
funzione deve poter chiamare `revoca_deleghe_di_ruolo` (in
`apps/accounts/deleghe.py`). È disaccoppiata da `Capo`: opera solo su
`Utente`, il chiamante in `anagrafica` risolve `capo.utente` prima di
chiamarla."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .deleghe import revoca_deleghe_di_ruolo
from .models import Ruolo, Utente


@transaction.atomic
def sincronizza_ruoli_cg(
    *, utente: Utente | None, gruppi_capogruppo: frozenset[str], assegnato_da: Utente | None = None
) -> None:
    """Allinea i Ruolo(tipo=CG, origine=DERIVATO) di `utente` all'insieme
    corrente di gruppi in cui il capo collegato è CAPO_GRUPPO. Se `utente` è
    None non c'è nulla da aprire/chiudere (D-30: "la sincronizzazione agisce
    sul Ruolo solo se il capo ha un account collegato"). Un capo può avere
    incarichi CAPO_GRUPPO attivi in più gruppi di servizio contemporaneamente:
    `gruppi_capogruppo` è un insieme, non una coppia vecchio/nuovo gruppo."""
    if utente is None:
        return

    oggi = timezone.localdate()

    ruoli_cg_attivi = list(
        Ruolo.objects.filter(
            utente=utente, tipo=Ruolo.Tipo.CG, origine=Ruolo.Origine.DERIVATO, attivo=True
        )
    )
    gruppi_con_ruolo = {r.gruppo_id for r in ruoli_cg_attivi}

    for ruolo in ruoli_cg_attivi:
        if ruolo.gruppo_id not in gruppi_capogruppo:
            ruolo.attivo = False
            ruolo.data_fine = oggi
            ruolo.save(update_fields=["attivo", "data_fine"])
            revoca_deleghe_di_ruolo(ruolo)

    for gruppo_codice in gruppi_capogruppo - gruppi_con_ruolo:
        ruolo = Ruolo(
            utente=utente,
            tipo=Ruolo.Tipo.CG,
            gruppo_id=gruppo_codice,
            attivo=True,
            data_inizio=oggi,
            origine=Ruolo.Origine.DERIVATO,
            assegnato_da=assegnato_da,
        )
        ruolo.full_clean()
        ruolo.save()
