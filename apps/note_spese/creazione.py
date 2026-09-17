"""Creazione della nota e delle sue righe documentali (F6c). Le righe di
categoria chilometrica (D-52/D-53, con ricerca località e duplicazione
andata/ritorno) restano fuori da questo modulo: interfaccia distinta,
rimandata a un passo successivo — qui c'è solo la nota in `BOZZA` e le
righe a importo inserito (D-45)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente
from apps.anagrafica.models import Capo, CensimentoCapo, IncaricoUnita

from .anno_associativo import anno_associativo_per_data
from .models import CategoriaSpesa, Evento, NotaSpese, RigaSpesa, StatoNota, TipoCalcolo
from .permessi import e_beneficiario_della_nota, e_compilatore_della_nota, puo_gestire_note


@transaction.atomic
def crea_nota_bozza(
    *,
    utente: Utente,
    beneficiario: Capo,
    evento: Evento,
    incarico: IncaricoUnita | None,
    incarico_altro: str,
    iban: str = "",
    intestatario_iban: str = "",
) -> NotaSpese:
    """D-36/D-44: crea la testata in `BOZZA`. Il gruppo di censimento è
    derivato da `CensimentoCapo` dell'anno associativo **corrente** (D-34) e
    congelato da qui in poi — non quello di spesa, ancora ignoto senza righe.

    **Inferenza dichiarata**: se chi compila per conto terzi (D-36) non ha a
    sua volta un `codice_socio` (account puramente funzionale), `compilatore`
    resta vuoto — i requisiti non specificano questo caso, che comunque resta
    tracciato da `NotaSpese.creata_da`."""
    e_per_conto_terzi = utente.codice_socio != beneficiario.pk
    if e_per_conto_terzi and not puo_gestire_note(utente):
        raise PermissionDenied(
            "Solo chi gestisce le note può crearne una per un altro capo (D-36)."
        )
    if incarico is not None and incarico.capo_id != beneficiario.pk:
        raise ValidationError(
            {"incarico": "L'incarico selezionato non appartiene al beneficiario."}
        )

    anno_corrente = anno_associativo_per_data(timezone.now().date())
    censimento = (
        CensimentoCapo.objects.select_related("gruppo")
        .filter(capo=beneficiario, anno_scout=anno_corrente)
        .first()
    )
    if censimento is None:
        raise ValidationError(f"{beneficiario} non risulta censito per l'anno {anno_corrente}.")

    compilatore = None
    if e_per_conto_terzi and utente.codice_socio is not None:
        compilatore = Capo.objects.filter(pk=utente.codice_socio).first()

    nota = NotaSpese(
        beneficiario=beneficiario,
        compilatore=compilatore,
        gruppo_censimento=censimento.gruppo,
        evento=evento,
        incarico=incarico,
        incarico_altro=incarico_altro,
        iban=iban,
        intestatario_iban=intestatario_iban,
        creata_da=utente,
    )
    nota.full_clean(exclude=["stato"])
    nota.save()
    return nota


def verifica_nota_modificabile(nota: NotaSpese, utente: Utente) -> None:
    """Condivisa da aggiunta righe e caricamento allegati (D-69): solo il
    beneficiario/compilatore (D-36) e solo mentre la nota è ancora in
    `BOZZA` — le altre fasi di modifica (`DA_INTEGRARE`/`DA_CONFERMARE`)
    sono F6d, non ancora coperte da questa funzione."""
    if not (e_beneficiario_della_nota(utente, nota) or e_compilatore_della_nota(utente, nota)):
        raise PermissionDenied(
            "Solo il beneficiario o chi ha compilato la nota per suo conto (D-36) può modificarla."
        )
    if nota.stato != StatoNota.BOZZA:
        raise ValidationError(
            "Si possono aggiungere righe o allegati solo mentre la nota è in bozza."
        )


@transaction.atomic
def aggiungi_riga_documentale(
    *,
    nota: NotaSpese,
    utente: Utente,
    categoria: CategoriaSpesa,
    data: datetime.date,
    importo: Decimal,
    descrizione: str = "",
    tratta_testo: str = "",
) -> RigaSpesa:
    """D-45: solo per categorie `DOCUMENTALE` — l'importo è un dato inserito,
    non derivato. Le categorie `CHILOMETRICO` passano da
    `calcolo_riga_auto.py`, mai da qui."""
    verifica_nota_modificabile(nota, utente)
    if not categoria.attivo:
        raise ValidationError({"categoria": "Categoria non più attiva."})
    if categoria.tipo_calcolo != TipoCalcolo.DOCUMENTALE:
        raise ValidationError(
            {
                "categoria": "Categoria di tipo chilometrico: l'importo si calcola, non si inserisce (D-45)."
            }
        )
    if categoria.descrizione_obbligatoria and not descrizione.strip():
        raise ValidationError(
            {"descrizione": "La descrizione è obbligatoria per questa categoria."}
        )
    if categoria.richiede_tratta and not tratta_testo.strip():
        raise ValidationError({"tratta_testo": "La tratta è obbligatoria per questa categoria."})
    riga = RigaSpesa(
        nota=nota,
        categoria=categoria,
        data=data,
        importo=importo,
        descrizione=descrizione,
        tratta_testo=tratta_testo,
    )
    riga.full_clean()
    riga.save()
    return riga
