"""Perimetro di visibilità delle note spese (D-65/D-66): il capo vede solo
le proprie (come beneficiario), segreteria/RdZ/admin vedono tutte — nessuna
distinzione di gruppo qui (D-65: il capogruppo non ha alcun privilegio in
più rispetto a un capo qualsiasi). Chi compila per conto terzi (D-36) è
sempre anche titolare di un ruolo di gestione (verificato in
`e_compilatore_della_nota`), quindi rientra già nel primo ramo: non serve un
terzo caso per il compilatore.

**Inferenza dichiarata**: i requisiti non specificano se le note in soft
delete (D-61) restino visibili a chi gestisce. Le escludo per entrambi i
perimetri — stessa ragione per cui una nota liquidata non è mai cancellabile
non vale al contrario: una nota "sparita" per il capo non deve ricomparire
in un elenco operativo di gestione. Se in fase di interfaccia (F6) serve un
elenco delle eliminate, va scritta una funzione a parte, non un parametro
qui."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import Utente

from .models import Allegato, NotaSpese
from .permessi import puo_gestire_note


def note_visibili(utente: Utente) -> QuerySet[NotaSpese]:
    base = NotaSpese.objects.filter(eliminata_il__isnull=True)
    if puo_gestire_note(utente):
        return base
    if utente.codice_socio is None:
        return base.none()
    return base.filter(beneficiario_id=utente.codice_socio)


def allegato_visibile(utente: Utente, allegato: Allegato) -> bool:
    """Un giustificativo è scaricabile solo se **tutte** le note a cui è
    collegato (un allegato cumulativo può coprire più righe, D-58) rientrano
    nel perimetro di `note_visibili()` — mai un controllo diretto su
    `Allegato.caricato_da`, che identifica solo chi l'ha caricato, non chi
    può vederlo (potrebbe averlo caricato la segreteria per conto del capo)."""
    note_id = set(allegato.righe.values_list("nota_id", flat=True))
    if not note_id:
        return False
    visibili = set(note_visibili(utente).filter(pk__in=note_id).values_list("pk", flat=True))
    return note_id <= visibili
