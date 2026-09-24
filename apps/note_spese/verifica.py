"""Vista di verifica per segreteria/RdZ (F6, §5.3): raccoglie, per ogni nota
"in lavorazione", le eccezioni non bloccanti già pronte nel service layer —
doppioni (D-57, `anti_doppione.py`, F4, mai ancora collegato a una view),
incarico non strutturato (D-50) — o estese qui, capienza indicativa (D-48).
Nessuna di queste blocca un flusso: sono solo segnalazioni da mostrare a chi
verifica, mai un errore restituito da `transizioni.py`."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import QuerySet

from apps.accounts.models import Utente

from .anti_doppione import (
    SegnalazionePasseggero,
    SegnalazioneTarga,
    segnalazioni_passeggero_con_propria_riga,
    segnalazioni_targa_sovrapposta,
)
from .budget import CapienzaCentroCosto, capienza_centro_costo
from .models import NotaSpese, StatoNota, TipoCalcolo
from .visibilita import note_visibili

# Stati "in lavorazione": dopo l'invio (una bozza non ha ancora nulla da
# verificare) e prima della chiusura (liquidata/respinta/annullata/decaduta
# non hanno più eccezioni operative da segnalare).
STATI_IN_LAVORAZIONE = (
    StatoNota.IN_VERIFICA,
    StatoNota.DA_INTEGRARE,
    StatoNota.DA_CONFERMARE,
    StatoNota.APPROVATA,
    StatoNota.AUTORIZZATA_RDZ,
)


@dataclass(frozen=True)
class EccezioniNota:
    nota: NotaSpese
    incarico_non_strutturato: bool
    doppioni_targa: list[SegnalazioneTarga] = field(default_factory=list)
    doppioni_passeggero: list[SegnalazionePasseggero] = field(default_factory=list)
    capienza: CapienzaCentroCosto | None = None

    @property
    def capienza_sforata(self) -> bool:
        """D-48: indicativo (consumato + impegnato), non il `residuo` certo
        di sola liquidazione — coerente con l'obbligo di dichiarare la
        differenza in interfaccia."""
        return self.capienza is not None and self.capienza.residuo_indicativo < 0

    @property
    def ha_eccezioni(self) -> bool:
        return bool(
            self.incarico_non_strutturato
            or self.doppioni_targa
            or self.doppioni_passeggero
            or self.capienza_sforata
        )


def note_in_verifica(utente: Utente) -> QuerySet[NotaSpese]:
    """Perimetro di `note_visibili()` (D-66), ristretto agli stati in
    lavorazione."""
    return (
        note_visibili(utente)
        .filter(stato__in=STATI_IN_LAVORAZIONE)
        .select_related("beneficiario", "evento", "centro_costo", "incarico")
        .prefetch_related("righe__categoria", "righe__passeggeri")
        # Ordinamento di default del model (-creata_il): le più recenti in cima.
    )


def eccezioni_nota(nota: NotaSpese) -> EccezioniNota:
    """Calcola le eccezioni di una singola nota. Le funzioni di
    `anti_doppione.py` girano per riga (interrogano il database ad ogni
    chiamata, non sono coperte dal `prefetch_related` di
    `note_in_verifica()`): accettabile per il volume di una coda di
    verifica, non pensato per un export massivo."""
    doppioni_targa: list[SegnalazioneTarga] = []
    doppioni_passeggero: list[SegnalazionePasseggero] = []
    for riga in nota.righe.all():
        if riga.categoria.tipo_calcolo != TipoCalcolo.CHILOMETRICO:
            continue
        doppioni_targa.extend(segnalazioni_targa_sovrapposta(riga))
        doppioni_passeggero.extend(segnalazioni_passeggero_con_propria_riga(riga))

    capienza = None
    if nota.centro_costo is not None:
        # D-48/§2 (decisione con Andrea, 2026-09-24): `anno_contabilizzazione`
        # resta nullo finché la nota non è liquidata (D-41), quindi la
        # capienza indicativa pre-liquidazione usa `anno_spesa` come proxy —
        # sempre valorizzato qui: le note "in lavorazione" sono già state
        # inviate (`invia_nota` lo assegna, F3), non sono più bozze.
        assert nota.anno_spesa is not None
        capienza = capienza_centro_costo(nota.centro_costo, nota.anno_spesa)

    return EccezioniNota(
        nota=nota,
        incarico_non_strutturato=nota.incarico_id is None,
        doppioni_targa=doppioni_targa,
        doppioni_passeggero=doppioni_passeggero,
        capienza=capienza,
    )
