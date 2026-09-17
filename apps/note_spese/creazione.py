"""Creazione della nota e delle sue righe (F6c): righe documentali (D-45,
importo inserito) e righe auto (D-52/D-53, importo calcolato). Il calcolo
vero e proprio resta in `calcolo_riga_auto.py` (F4): qui solo costruzione
della riga/dei passeggeri e chiamata al punto d'ingresso unico."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente
from apps.anagrafica.models import Capo, CensimentoCapo, IncaricoUnita

from .anno_associativo import anno_associativo_per_data
from .calcolo_riga_auto import calcola_importo_riga_auto
from .models import (
    CategoriaSpesa,
    Evento,
    Localita,
    NotaSpese,
    RigaSpesa,
    RigaSpesaPasseggero,
    SottotipoChilometrico,
    StatoNota,
    TipoCalcolo,
)
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


@transaction.atomic
def aggiungi_riga_auto(
    *,
    nota: NotaSpese,
    utente: Utente,
    categoria: CategoriaSpesa,
    data: datetime.date,
    localita_partenza: Localita,
    localita_arrivo: Localita,
    targa: str = "",
    passeggeri_capi: list[Capo] | None = None,
    passeggeri_nomi_liberi: list[str] | None = None,
) -> RigaSpesa:
    """D-52/D-53: solo per categorie `CHILOMETRICO`. L'importo non si passa
    qui: lo calcola e lo persiste `calcola_importo_riga_auto()` (F4), unico
    punto d'ingresso per non bypassare l'aggregazione andata/ritorno."""
    verifica_nota_modificabile(nota, utente)
    if not categoria.attivo:
        raise ValidationError({"categoria": "Categoria non più attiva."})
    if categoria.tipo_calcolo != TipoCalcolo.CHILOMETRICO:
        raise ValidationError(
            {"categoria": "Categoria documentale: l'importo si inserisce, non si calcola (D-45)."}
        )
    if localita_partenza.pk == localita_arrivo.pk:
        raise ValidationError({"localita_arrivo": "Partenza e arrivo non possono coincidere."})

    riga = RigaSpesa(
        nota=nota,
        categoria=categoria,
        data=data,
        localita_partenza=localita_partenza,
        localita_arrivo=localita_arrivo,
        targa=targa,
    )
    riga.full_clean()
    riga.save()

    for capo in passeggeri_capi or []:
        RigaSpesaPasseggero.objects.create(riga=riga, capo=capo)
    for nome in passeggeri_nomi_liberi or []:
        RigaSpesaPasseggero.objects.create(riga=riga, nome_libero=nome)

    calcola_importo_riga_auto(riga)
    return riga


@transaction.atomic
def duplica_riga_andata_ritorno(
    *, riga: RigaSpesa, utente: Utente, nuova_data: datetime.date
) -> RigaSpesa:
    """D-53: crea il viaggio di ritorno da uno già inserito, invertendo
    partenza/arrivo e riportando stessa targa e stessi passeggeri — l'utente
    cambia solo la data. Solo per la sottocategoria 'Auto andata e ritorno':
    'Altri spostamenti' non ha un concetto di viaggio simmetrico da duplicare."""
    verifica_nota_modificabile(riga.nota, utente)
    if riga.categoria.sottotipo_chilometrico != SottotipoChilometrico.ANDATA_RITORNO:
        raise ValidationError("Si può duplicare solo una riga 'Auto (andata e ritorno)'.")
    if riga.localita_partenza_id is None or riga.localita_arrivo_id is None:
        raise ValidationError("La riga non ha ancora partenza e arrivo definiti.")

    nuova = RigaSpesa(
        nota=riga.nota,
        categoria=riga.categoria,
        data=nuova_data,
        localita_partenza=riga.localita_arrivo,
        localita_arrivo=riga.localita_partenza,
        targa=riga.targa,
    )
    nuova.full_clean()
    nuova.save()

    for passeggero in riga.passeggeri.all():
        RigaSpesaPasseggero.objects.create(
            riga=nuova, capo_id=passeggero.capo_id, nome_libero=passeggero.nome_libero
        )

    calcola_importo_riga_auto(nuova)
    return nuova
