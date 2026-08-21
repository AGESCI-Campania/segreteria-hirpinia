"""Service layer dell'export anagrafica (D-23): unico punto che genera le
righe esportabili. View e comandi di gestione devono chiamare
`genera_righe_esportazione()`, mai reimplementare i filtri o il perimetro qui
dentro (CLAUDE.md).

**Inferenza dichiarata** (non specificata letteralmente in D-23): il
"livello Fo.Ca." di riga/filtro/raggruppamento è `CensimentoCapo.livello_foca`
(il livello di formazione della persona, dal CSV anagrafico), non
`IncaricoUnita.livello_foca` (per singolo incarico, dal PDF). La scelta
rende il valore stabile per persona, indipendente da quanti incarichi ha, e
risolve senza ambiguità il caso dei capi "a disposizione" (che non hanno
alcun IncaricoUnita ma un livello Fo.Ca. lo hanno comunque)."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import gruppi_visibili

from .models import (
    A_DISPOSIZIONE,
    BrancaUnita,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    ProfiloColonneEsportazione,
    RaggruppamentoEsportazione,
    StatoFiltroEsportazione,
)
from .visibilita import capi_visibili

# Testo convenzionale, non ricavato da un IncaricoUnita reale (D-31: nessun
# record sintetico): i capi "a disposizione" non hanno un'unità, ma la
# convenzione AGESCI li considera comunque assegnati alla Comunità Capi.
_UNITA_A_DISPOSIZIONE = "COMUNITA' CAPI"

# CG incluso (esporta il proprio gruppo, D-23); SEGRETERIA/ADMIN/RDZ tutta la
# Zona via gruppi_visibili().
RUOLI_EXPORT_ANAGRAFICA = frozenset(
    {Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ, Ruolo.Tipo.CG}
)

# Il registro delle esportazioni è visibile solo ad ADMIN (D-23).
RUOLI_VISUALIZZAZIONE_ESPORTAZIONI = frozenset({Ruolo.Tipo.ADMIN})


@dataclass(frozen=True)
class FiltriEsportazione:
    """`gruppo`/`unita`/`funzione`/`livello_foca` sono tuple: una o più
    scelte, tupla vuota = nessun filtro su quel campo (D-23, filtri
    multi-selezione)."""

    anno_scout: int
    gruppo: tuple[str, ...] = ()
    unita: tuple[str, ...] = ()
    branca: tuple[str, ...] = ()
    funzione: tuple[str, ...] = ()
    livello_foca: tuple[int, ...] = ()
    stato: str = StatoFiltroEsportazione.ATTIVI
    raggruppamento: str = RaggruppamentoEsportazione.NESSUNO
    profilo_colonne: str = ProfiloColonneEsportazione.MINIMO


@dataclass(frozen=True)
class RigaEsportazione:
    codice_socio: str
    cognome: str
    nome: str
    gruppo_censimento_codice: str
    gruppo_censimento_nome: str
    gruppo_servizio_codice: str
    gruppo_servizio_nome: str
    codice_unita: str
    nome_unita: str
    branca: str
    branca_label: str
    funzione: str
    funzione_label: str
    livello_foca: int | None
    attivo: bool
    sesso: str = ""
    data_nascita: datetime.date | None = None
    comune_nascita: str = ""
    codice_fiscale: str = ""
    nazionalita: str = ""
    indirizzo: str = ""
    civico: str = ""
    comune_residenza: str = ""
    provincia_residenza: str = ""
    cap: str = ""
    email: str = ""
    cellulare: str = ""
    professione: str = ""


def genera_righe_esportazione(utente: Utente, filtri: FiltriEsportazione) -> list[RigaEsportazione]:
    """Perimetro (D-23: CG solo i propri capi, SEGRETERIA/ADMIN/RDZ tutta la
    Zona) applicato sia sulla selezione dei capi (censimento O servizio,
    `capi_visibili`) sia, se `filtri.gruppo` è valorizzato, come controllo
    esplicito: filtrare per un gruppo fuori perimetro non deve restituire un
    risultato vuoto silenzioso, ma un errore — anche con più gruppi
    selezionati, basta che uno solo sia fuori perimetro."""
    if filtri.gruppo:
        visibili = {g.codice for g in gruppi_visibili(utente, filtri.anno_scout)}
        fuori_perimetro = set(filtri.gruppo) - visibili
        if fuori_perimetro:
            raise PermissionDenied(
                f"{utente}: {', '.join(sorted(fuori_perimetro))} non è/sono nel proprio "
                "perimetro operativo."
            )

    censimenti: QuerySet[CensimentoCapo] = capi_visibili(utente, filtri.anno_scout).select_related(
        "capo", "gruppo"
    )

    if filtri.livello_foca:
        censimenti = censimenti.filter(livello_foca__in=filtri.livello_foca)
    if filtri.stato == StatoFiltroEsportazione.ATTIVI:
        censimenti = censimenti.filter(capo__attivo=True)
    elif filtri.stato == StatoFiltroEsportazione.DISATTIVATI:
        censimenti = censimenti.filter(capo__attivo=False)

    righe: list[RigaEsportazione] = []
    for censimento in censimenti.order_by("capo__cognome", "capo__nome"):
        incarichi = list(
            IncaricoUnita.objects.filter(
                capo_id=censimento.capo_id, anno_scout=filtri.anno_scout, cessato_il__isnull=True
            ).select_related("gruppo_servizio")
        )
        righe.extend(_righe_capo(censimento, incarichi, filtri))
    return righe


def _dati_base(censimento: CensimentoCapo) -> dict:
    capo = censimento.capo
    return {
        "codice_socio": censimento.capo_id,
        "cognome": capo.cognome,
        "nome": capo.nome,
        "gruppo_censimento_codice": censimento.gruppo_id,
        "gruppo_censimento_nome": censimento.gruppo.nome,
        "livello_foca": censimento.livello_foca,
        "attivo": capo.attivo,
        "sesso": capo.sesso,
        "data_nascita": capo.data_nascita,
        "comune_nascita": capo.comune_nascita,
        "codice_fiscale": capo.codice_fiscale,
        "nazionalita": capo.nazionalita,
        "indirizzo": capo.indirizzo,
        "civico": capo.civico,
        "comune_residenza": capo.comune_residenza,
        "provincia_residenza": capo.provincia_residenza,
        "cap": capo.cap,
        "email": capo.email,
        "cellulare": capo.cellulare,
        "professione": capo.professione,
    }


def _righe_capo(
    censimento: CensimentoCapo, incarichi: list[IncaricoUnita], filtri: FiltriEsportazione
) -> list[RigaEsportazione]:
    base = _dati_base(censimento)

    if not incarichi:
        if not _passa_filtri_a_disposizione(censimento, filtri):
            return []
        return [
            RigaEsportazione(
                **base,
                gruppo_servizio_codice="",
                gruppo_servizio_nome="",
                codice_unita="",
                nome_unita=_UNITA_A_DISPOSIZIONE,
                branca=BrancaUnita.ADULTI,
                branca_label=BrancaUnita.ADULTI.label,
                funzione=A_DISPOSIZIONE,
                funzione_label="A disposizione",
            )
        ]

    righe = []
    for incarico in incarichi:
        if not _passa_filtri_incarico(incarico, filtri):
            continue
        righe.append(
            RigaEsportazione(
                **base,
                gruppo_servizio_codice=incarico.gruppo_servizio_id,
                gruppo_servizio_nome=incarico.gruppo_servizio.nome,
                codice_unita=incarico.codice_unita,
                nome_unita=incarico.nome_unita,
                branca=incarico.branca,
                branca_label=BrancaUnita(incarico.branca).label,
                funzione=incarico.funzione,
                funzione_label=FunzioneIncarico(incarico.funzione).label,
            )
        )
    return righe


def _passa_filtri_a_disposizione(censimento: CensimentoCapo, filtri: FiltriEsportazione) -> bool:
    if filtri.funzione and A_DISPOSIZIONE not in filtri.funzione:
        return False
    if filtri.unita:
        return False
    if filtri.branca and BrancaUnita.ADULTI not in filtri.branca:
        return False
    if filtri.gruppo and censimento.gruppo_id not in filtri.gruppo:
        return False
    return True


def _passa_filtri_incarico(incarico: IncaricoUnita, filtri: FiltriEsportazione) -> bool:
    if filtri.funzione and incarico.funzione not in filtri.funzione:
        return False
    if filtri.unita and incarico.codice_unita not in filtri.unita:
        return False
    if filtri.branca and incarico.branca not in filtri.branca:
        return False
    if filtri.gruppo and incarico.gruppo_servizio_id not in filtri.gruppo:
        return False
    return True


# ── Colonne e raggruppamento ────────────────────────────────────────────────


def etichetta_unita(codice_unita: str, nome_unita: str) -> str:
    """`nome (codice)` quando c'è un nome, altrimenti solo il codice — mai il
    solo codice quando un nome è disponibile (richiesta beta). Senza codice
    (solo i capi "a disposizione", D-31) resta il solo nome convenzionale
    "COMUNITA' CAPI"."""
    if not codice_unita:
        return nome_unita
    return f"{nome_unita} ({codice_unita})" if nome_unita else codice_unita


_ColonnaEsportazione = tuple[str, Callable[[RigaEsportazione], object]]

_COLONNE_MINIMO: list[_ColonnaEsportazione] = [
    ("Codice socio", lambda r: r.codice_socio),
    ("Cognome", lambda r: r.cognome),
    ("Nome", lambda r: r.nome),
    ("Gruppo censimento", lambda r: r.gruppo_censimento_codice),
    ("Gruppo servizio", lambda r: r.gruppo_servizio_codice),
    ("Unità", lambda r: etichetta_unita(r.codice_unita, r.nome_unita)),
    ("Branca", lambda r: r.branca_label),
    ("Funzione", lambda r: r.funzione_label),
    ("Livello Fo.Ca.", lambda r: r.livello_foca if r.livello_foca is not None else ""),
]

_COLONNE_ESTESE_AGGIUNTIVE: list[_ColonnaEsportazione] = [
    ("Attivo", lambda r: "Sì" if r.attivo else "No"),
    ("Sesso", lambda r: r.sesso),
    ("Data di nascita", lambda r: r.data_nascita.isoformat() if r.data_nascita else ""),
    ("Comune di nascita", lambda r: r.comune_nascita),
    ("Codice fiscale", lambda r: r.codice_fiscale),
    ("Nazionalità", lambda r: r.nazionalita),
    ("Indirizzo", lambda r: r.indirizzo),
    ("Civico", lambda r: r.civico),
    ("Comune di residenza", lambda r: r.comune_residenza),
    ("Provincia di residenza", lambda r: r.provincia_residenza),
    ("CAP", lambda r: r.cap),
    ("Email", lambda r: r.email),
    ("Cellulare", lambda r: r.cellulare),
    ("Professione", lambda r: r.professione),
]


def colonne_per_profilo(profilo: str) -> list[_ColonnaEsportazione]:
    if profilo == ProfiloColonneEsportazione.ESTESO:
        return _COLONNE_MINIMO + _COLONNE_ESTESE_AGGIUNTIVE
    return list(_COLONNE_MINIMO)


def _chiave_raggruppamento(riga: RigaEsportazione, raggruppamento: str) -> str:
    if raggruppamento == RaggruppamentoEsportazione.PER_UNITA:
        return etichetta_unita(riga.codice_unita, riga.nome_unita) or "A disposizione"
    if raggruppamento == RaggruppamentoEsportazione.PER_BRANCA:
        return riga.branca_label
    if raggruppamento == RaggruppamentoEsportazione.PER_FUNZIONE:
        return riga.funzione_label
    if raggruppamento == RaggruppamentoEsportazione.PER_LIVELLO_FOCA:
        return str(riga.livello_foca) if riga.livello_foca is not None else "Non indicato"
    return ""


def ordina_per_raggruppamento(
    righe: list[RigaEsportazione], raggruppamento: str
) -> list[RigaEsportazione]:
    """Per il CSV, che non ha fogli: il raggruppamento diventa ordinamento
    sulla colonna già presente fra quelle del profilo (D-23)."""
    if raggruppamento == RaggruppamentoEsportazione.NESSUNO:
        return righe
    return sorted(righe, key=lambda r: _chiave_raggruppamento(r, raggruppamento))


def raggruppa_righe(
    righe: list[RigaEsportazione], raggruppamento: str
) -> dict[str, list[RigaEsportazione]]:
    """Per l'xlsx: un foglio per valore del raggruppamento (D-23)."""
    if raggruppamento == RaggruppamentoEsportazione.NESSUNO:
        return {"Capi": righe}
    gruppi: dict[str, list[RigaEsportazione]] = {}
    for riga in righe:
        chiave = _chiave_raggruppamento(riga, raggruppamento)
        gruppi.setdefault(chiave, []).append(riga)
    return dict(sorted(gruppi.items())) or {"Capi": []}
