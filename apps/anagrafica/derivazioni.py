"""Derivazioni condivise fra l'import PDF (M3) e l'assegnazione manuale di
incarichi (M3b): unica fonte di verità, chiamata da entrambi i chiamanti
(CLAUDE.md — "se ti accorgi di scrivere due volte la stessa regola,
fermati"). Non scrivere mai questa logica altrove."""

from __future__ import annotations

from .models import (
    Branca,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    MembroPattuglia,
    Pattuglia,
)

# Priorità dichiarata come inferenza (non specificata letteralmente dal
# documento di progettazione, che dice solo "prima branca fra LC/EG/RS
# presente"): l'ordine è quello della tabella D-08.
_PRIORITA_BRANCA = (Branca.LC, Branca.EG, Branca.RS)

_MAPPA_FUNZIONE_SG_AE: dict[str, str] = {
    FunzioneIncarico.SUPPORTO_GRUPPO: Branca.SG,
    FunzioneIncarico.SUPPORTO_AZIONE_EDUCATIVA: Branca.SG,
    FunzioneIncarico.AE_GRUPPO: Branca.AE,
    FunzioneIncarico.AE_UNITA: Branca.AE,
}


def _deriva_branca_capo(funzioni_branche: set[tuple[str, str]], branca_attuale: str) -> str:
    """§6.2: "prima branca fra LC/EG/RS presente negli incarichi del capo; se
    assente, SUPPORTO_GRUPPO/SUPPORTO_AZIONE_EDUCATIVA -> SG,
    AE_GRUPPO/AE_UNITA -> AE; altrimenti invariata." A differenza di
    is_capogruppo/a_disposizione, qui il valore NON si azzera se non emerge
    nessuna corrispondenza."""
    branche_unita_presenti = {b for _f, b in funzioni_branche}
    for candidata in _PRIORITA_BRANCA:
        if candidata in branche_unita_presenti:
            return candidata

    for funzione, _branca_unita in funzioni_branche:
        if funzione in _MAPPA_FUNZIONE_SG_AE:
            return _MAPPA_FUNZIONE_SG_AE[funzione]

    return branca_attuale


def ricalcola_derivati_capo(capo_id: str, anno_scout: int) -> CensimentoCapo | None:
    """Rilegge gli IncaricoUnita attivi del capo per l'anno su TUTTI i gruppi
    di servizio (D-34) e riscrive branca/is_capogruppo/a_disposizione sul suo
    CensimentoCapo dell'anno. `is_capogruppo` e `a_disposizione` sono sempre
    azzerati e ricalcolati da zero (D-08, D-31); `branca` resta invariata se
    nessun incarico la determina (§6.2). Ritorna None se il capo non ha un
    CensimentoCapo per quell'anno (incarico su un capo non censito nell'anno,
    caso limite non impedito a monte)."""
    censimento = CensimentoCapo.objects.filter(capo_id=capo_id, anno_scout=anno_scout).first()
    if censimento is None:
        return None

    attivi = IncaricoUnita.objects.filter(
        capo_id=capo_id, anno_scout=anno_scout, cessato_il__isnull=True
    )
    funzioni_branche = set(attivi.values_list("funzione", "branca"))
    funzioni = {f for f, _b in funzioni_branche}

    censimento.is_capogruppo = FunzioneIncarico.CAPO_GRUPPO in funzioni
    censimento.a_disposizione = not attivi.exists()
    censimento.branca = _deriva_branca_capo(funzioni_branche, censimento.branca)
    censimento.save(update_fields=["is_capogruppo", "a_disposizione", "branca"])
    return censimento


def ricalcola_pattuglia(branca: str, anno_scout: int) -> None:
    """Ricostruisce da zero l'appartenenza alla pattuglia di (branca, anno)
    dai CensimentoCapo correnti. Applicabile solo per LC/EG/RS: le altre
    branche non generano pattuglia."""
    if branca not in Pattuglia.BRANCHE_AMMESSE:
        return

    pattuglia, _creata = Pattuglia.objects.get_or_create(branca=branca, anno_scout=anno_scout)
    capi_attesi = set(
        CensimentoCapo.objects.filter(anno_scout=anno_scout, branca=branca).values_list(
            "capo_id", flat=True
        )
    )
    capi_attuali = set(pattuglia.membri.values_list("capo_id", flat=True))

    da_rimuovere = capi_attuali - capi_attesi
    if da_rimuovere:
        MembroPattuglia.objects.filter(pattuglia=pattuglia, capo_id__in=da_rimuovere).delete()

    da_aggiungere = capi_attesi - capi_attuali
    if da_aggiungere:
        MembroPattuglia.objects.bulk_create(
            [MembroPattuglia(pattuglia=pattuglia, capo_id=capo_id) for capo_id in da_aggiungere]
        )
