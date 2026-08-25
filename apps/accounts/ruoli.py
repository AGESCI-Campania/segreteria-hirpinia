"""Creazione e revoca di un ruolo esplicito (RDZ/ADMIN/SEGRETERIA/ecc., D-35,
M11). Prima di queste funzioni l'unica via era la modifica diretta dei campi
da Django admin, senza cascata sulle deleghe collegate: colmano quel gap e,
per RDZ, richiamano la sincronizzazione del CG derivato su E9001."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .deleghe import revoca_deleghe_di_ruolo
from .models import Ruolo, Utente
from .permessi import ruoli_effettivi
from .ruoli_derivati import sincronizza_cg_comitato_zona

RUOLI_GESTIONE_RUOLI = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})

# M11: CG escluso di proposito — resta derivato da incarico (D-30) o dal
# percorso invito-con-gruppo esistente, per non aprire un terzo punto di
# scrittura da tenere allineato a D-35 (un solo gruppo reale, 2 CG/1M+1F).
TIPI_RUOLO_ASSEGNABILI_DIRETTAMENTE = frozenset(t for t in Ruolo.Tipo if t != Ruolo.Tipo.CG)


def _verifica_ruolo_gestione_ruoli(utente: Utente) -> None:
    ruoli = [r for r in ruoli_effettivi(utente) if not r.is_delega]
    if not any(r.tipo in RUOLI_GESTIONE_RUOLI for r in ruoli):
        raise PermissionDenied(f"{utente}: azione riservata a SEGRETERIA/ADMIN/RDZ diretti.")


@transaction.atomic
def revoca_ruolo_esplicito(*, utente: Utente, ruolo: Ruolo) -> None:
    """Chiude un ruolo di `origine=AMMINISTRATIVO` (mai un ruolo derivato: quelli
    sono gestiti solo da `sincronizza_ruoli_cg`/`sincronizza_cg_comitato_zona`,
    mai chiusi a mano). Nel mondo reale la revoca segue sempre un atto
    amministrativo esplicito — delibera della Comunità Capi, o dell'Assemblea
    di Zona per E9001, o dimissioni (D-35) — mai un effetto collaterale
    automatico di altri dati: per questo non esiste alcuna logica che la
    inneschi da sola."""
    _verifica_ruolo_gestione_ruoli(utente)

    if ruolo.origine == Ruolo.Origine.DERIVATO:
        raise ValueError(
            f"{ruolo}: ruolo derivato, non si revoca direttamente "
            "(si chiude da solo quando cessa la condizione che lo genera)."
        )

    if not ruolo.attivo:
        return

    oggi = timezone.localdate()
    ruolo.attivo = False
    ruolo.data_fine = oggi
    ruolo.save(update_fields=["attivo", "data_fine"])
    revoca_deleghe_di_ruolo(ruolo)

    if ruolo.tipo == Ruolo.Tipo.RDZ:
        sincronizza_cg_comitato_zona(utente=ruolo.utente)


@transaction.atomic
def crea_ruolo_esplicito(
    *,
    utente_assegnante: Utente,
    utente_destinatario: Utente,
    tipo: str,
    branca: str = "",
    settore: str = "",
    data_fine=None,
) -> Ruolo:
    """Assegna un ruolo amministrativo a un utente già attivo, senza passare
    dall'invito OTP (M11). `tipo` esclude sempre `Ruolo.Tipo.CG` (vedi
    `TIPI_RUOLO_ASSEGNABILI_DIRETTAMENTE`): un tentativo di assegnarlo da qui
    è un errore di programmazione della view, non un input utente da
    accettare in silenzio."""
    _verifica_ruolo_gestione_ruoli(utente_assegnante)

    if tipo not in TIPI_RUOLO_ASSEGNABILI_DIRETTAMENTE:
        raise ValueError(f"{tipo}: non assegnabile da qui (CG deriva da incarico o da invito).")

    duplicato = Ruolo.objects.filter(
        utente=utente_destinatario, tipo=tipo, branca=branca, settore=settore, attivo=True
    ).exists()
    if duplicato:
        raise ValidationError(
            f"{utente_destinatario} ha già un ruolo {tipo} attivo identico: nessun doppione."
        )

    ruolo = Ruolo(
        utente=utente_destinatario,
        tipo=tipo,
        branca=branca,
        settore=settore,
        data_fine=data_fine,
        assegnato_da=utente_assegnante,
        origine=Ruolo.Origine.AMMINISTRATIVO,
    )
    ruolo.full_clean()
    ruolo.save()

    if tipo == Ruolo.Tipo.RDZ:
        sincronizza_cg_comitato_zona(utente=utente_destinatario)

    return ruolo
