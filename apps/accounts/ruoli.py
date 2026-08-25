"""Revoca di un ruolo esplicito (RDZ/ADMIN/SEGRETERIA/ecc., D-35). Prima di
questa funzione l'unica via era la modifica diretta dei campi da Django admin,
senza cascata sulle deleghe collegate: colma quel gap e, per RDZ, richiama la
sincronizzazione del CG derivato su E9001."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .deleghe import revoca_deleghe_di_ruolo
from .models import Ruolo, Utente
from .permessi import ruoli_effettivi
from .ruoli_derivati import sincronizza_cg_comitato_zona

RUOLI_GESTIONE_RUOLI = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


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
