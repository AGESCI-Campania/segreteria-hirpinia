"""Inserimento manuale di una partecipazione (§7 passo 2). Logica ramificata
reale (perimetro, capo attivo/censito/non-E9001, stato/finestra campagna,
precompilazione quota_versata) — non un full_clean()+save() nudo in view,
stesso principio già applicato in
apps/anagrafica/incarichi.py::assegna_incarico_manuale per un inserimento
singolo con verifica di perimetro."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import gruppi_visibili
from apps.anagrafica.models import CensimentoCapo
from apps.organizzazione.models import Gruppo

from .models import Campagna, Partecipazione, StatoCampagna, TipologiaCampo

# D-21/D-32 hanno lo stesso perimetro: CG sul proprio gruppo, SEGRETERIA/ADMIN/RDZ
# su tutta la Zona.
RUOLI_GESTIONE_PARTECIPAZIONI = frozenset(
    {Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ, Ruolo.Tipo.CG}
)


def risolvi_gruppo_competente(utente: Utente, codice_socio: str, *, anno_scout: int) -> Gruppo:
    """Condivisa da inserimento manuale e da D-21. Il perimetro è quello del
    CENSIMENTO (D-34), mai del servizio. Esclude esplicitamente i censiti in
    E9001 (A-8): né gruppi_visibili() né GruppoQuerySet.attivi() lo fanno, e
    senza questo controllo un SEGRETERIA/ADMIN/RDZ potrebbe altrimenti creare
    una partecipazione per un censito in E9001."""
    censimento = (
        CensimentoCapo.objects.select_related("capo", "gruppo")
        .filter(capo_id=codice_socio, anno_scout=anno_scout)
        .first()
    )
    if censimento is None:
        raise ValidationError(f"{codice_socio}: non censito nell'anno {anno_scout}.")
    if not censimento.capo.attivo:
        raise ValidationError(f"{codice_socio}: capo non attivo.")
    if censimento.gruppo.is_comitato_zona:
        raise ValidationError(f"{codice_socio}: censito in E9001, escluso dal contributo (A-8).")

    visibili = {g.codice for g in gruppi_visibili(utente, anno_scout)}
    if censimento.gruppo_id not in visibili:
        raise PermissionDenied(f"{censimento.gruppo_id} non è nel perimetro di {utente}.")
    return censimento.gruppo


@transaction.atomic
def inserisci_partecipazione_manuale(
    *,
    utente: Utente,
    campagna: Campagna,
    codice_socio: str,
    tipologia: TipologiaCampo,
    data_inizio: datetime.date,
    data_fine: datetime.date,
    luogo: str,
    quota_versata: Decimal | None,
    descrizione_altro: str = "",
) -> Partecipazione:
    if campagna.stato != StatoCampagna.APERTA or not campagna.in_finestra_inserimento():
        raise ValidationError("La campagna non è aperta all'inserimento o è fuori finestra (D-21).")

    gruppo = risolvi_gruppo_competente(utente, codice_socio, anno_scout=campagna.anno)

    quota = quota_versata if quota_versata is not None else tipologia.quota_default
    if quota is None:
        raise ValidationError(
            "Nessuna quota_versata indicata e la tipologia non ha una quota di default."
        )

    partecipazione = Partecipazione(
        campagna=campagna,
        capo_id=codice_socio,
        gruppo=gruppo,
        tipologia=tipologia,
        descrizione_altro=descrizione_altro,
        data_inizio=data_inizio,
        data_fine=data_fine,
        luogo=luogo,
        quota_versata=quota,
        inserita_da=utente,
    )
    # exclude=["stato"]: vedi commento identico in campagne.py::apri_campagna.
    partecipazione.full_clean(exclude=["stato"])
    partecipazione.save()
    return partecipazione
