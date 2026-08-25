"""Sincronizzazione dei ruoli `CG` derivati: dall'incarico di capogruppo
(D-30) e dal ruolo `RDZ` per il CG di `E9001` (D-35). Vive in `accounts` e non
in `anagrafica` per evitare un import circolare: `apps.anagrafica.importazione*`
importa già `apps.accounts.models`, e queste funzioni devono poter chiamare
`revoca_deleghe_di_ruolo` (in `apps/accounts/deleghe.py`). `sincronizza_ruoli_cg`
è disaccoppiata da `Capo`: opera solo su `Utente`, il chiamante in `anagrafica`
risolve `capo.utente` prima di chiamarla."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.organizzazione.models import Gruppo

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


@transaction.atomic
def sincronizza_cg_comitato_zona(*, utente: Utente) -> None:
    """Allinea il Ruolo(tipo=CG, gruppo=E9001, origine=DERIVATO) di `utente`
    al possesso di un ruolo RDZ attivo **diretto** (D-35, corregge D-33): un
    RDZ per delega non fa nascere un CG derivato, coerente con
    `_e_admin_diretto()` in `permessi.py` per lo stesso genere di distinzione.
    E9001 non è un gruppo reale (D-35): questo CG derivato può coesistere con
    l'eventuale CG (derivato o amministrativo) dell'utente sul proprio gruppo
    di censimento, è l'unica eccezione al vincolo "un solo gruppo reale"."""
    oggi = timezone.localdate()
    e9001 = Gruppo.objects.filter(is_comitato_zona=True).first()
    if e9001 is None:
        return

    ha_rdz_diretto = Ruolo.objects.filter(utente=utente, tipo=Ruolo.Tipo.RDZ, attivo=True).exists()

    ruolo_cg_e9001 = Ruolo.objects.filter(
        utente=utente,
        tipo=Ruolo.Tipo.CG,
        gruppo=e9001,
        origine=Ruolo.Origine.DERIVATO,
        attivo=True,
    ).first()

    if ha_rdz_diretto and ruolo_cg_e9001 is None:
        ruolo = Ruolo(
            utente=utente,
            tipo=Ruolo.Tipo.CG,
            gruppo=e9001,
            attivo=True,
            data_inizio=oggi,
            origine=Ruolo.Origine.DERIVATO,
        )
        ruolo.full_clean()
        ruolo.save()
    elif not ha_rdz_diretto and ruolo_cg_e9001 is not None:
        ruolo_cg_e9001.attivo = False
        ruolo_cg_e9001.data_fine = oggi
        ruolo_cg_e9001.save(update_fields=["attivo", "data_fine"])
        revoca_deleghe_di_ruolo(ruolo_cg_e9001)
