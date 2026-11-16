"""Registro delle operazioni di un'assemblea: le voci di django-auditlog dei
modelli del modulo (registrati in apps.py), ricondotte all'assemblea a cui
appartengono. Lo vedono solo amministratori e RdZ
(`permessi.puo_vedere_registro`).

Una voce si riconduce all'assemblea risalendo la catena delle chiavi esterne
(`GENITORE`): per gli oggetti ancora presenti dal database, per quelli eliminati
dai valori registrati nella voce stessa (auditlog salva tutti i campi alla
creazione e all'eliminazione). Così il registro copre anche le voci scritte
prima che esistesse."""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from .models import (
    Appello,
    Assemblea,
    AventeDiritto,
    Candidato,
    Candidatura,
    DelegaAE,
    IncaricoAssemblea,
    IncaricoDichiarato,
    OperatoreVoto,
    PosizioneVoto,
    Presenza,
    PuntoOdG,
    RigaProgramma,
    RisultatoCanale,
    Seduta,
    SottopuntoOdG,
    VariazioneRappresentante,
    VerbaleSeduta,
    Votazione,
)

# Modello registrato in auditlog → campo che porta al genitore, fino ad Assemblea.
GENITORE: dict[type[models.Model], str] = {
    Seduta: "assemblea",
    AventeDiritto: "assemblea",
    OperatoreVoto: "assemblea",
    IncaricoAssemblea: "assemblea",
    PuntoOdG: "assemblea",
    PosizioneVoto: "assemblea",
    Appello: "seduta",
    DelegaAE: "seduta",
    RigaProgramma: "seduta",
    Votazione: "seduta",
    VerbaleSeduta: "seduta",
    VariazioneRappresentante: "seduta",
    Presenza: "appello",
    IncaricoDichiarato: "avente",
    SottopuntoOdG: "punto",
    Candidatura: "posizione",
    RisultatoCanale: "votazione",
    Candidato: "votazione",
}

MODELLI: list[type[models.Model]] = [Assemblea, *GENITORE]

NULLO = "None"

AZIONI = {
    LogEntry.Action.CREATE: "Creazione",
    LogEntry.Action.UPDATE: "Modifica",
    LogEntry.Action.DELETE: "Eliminazione",
}


@dataclasses.dataclass(frozen=True)
class Modifica:
    campo: str
    prima: str
    dopo: str


@dataclasses.dataclass(frozen=True)
class Voce:
    quando: datetime.datetime
    autore: str
    eseguito_da_reale: str
    indirizzo: str
    azione: str
    tipo: str
    oggetto: str
    modifiche: list[Modifica]


def tipi_oggetto() -> list[tuple[str, str]]:
    """(nome del modello, descrizione) per il filtro della pagina."""
    return sorted(
        ((m._meta.model_name or "", str(m._meta.verbose_name).capitalize()) for m in MODELLI),
        key=lambda t: t[1],
    )


def _valore_genitore(changes: dict, campo: str) -> str | None:
    valori = changes.get(campo)
    if not valori:
        return None
    valore = next((v for v in valori if v not in (NULLO, None, "")), None)
    return str(valore) if valore is not None else None


Genitori = dict[tuple[Any, str], tuple[Any, str]]


def _genitori(voci: list[LogEntry], per_tipo: dict[int, type[models.Model]]) -> Genitori:
    """(modello, pk) → (modello del genitore, pk del genitore)."""
    genitori: Genitori = {}
    for modello, campo in GENITORE.items():
        padre = modello._meta.get_field(campo).related_model
        for pk, fk in modello._default_manager.values_list("pk", f"{campo}_id"):
            genitori[(modello, str(pk))] = (padre, str(fk))
    for voce in voci:
        modello = per_tipo[voce.content_type_id]
        nome_campo = GENITORE.get(modello)
        if nome_campo is None or (modello, voce.object_pk) in genitori:
            continue
        valore = _valore_genitore(voce.changes or {}, nome_campo)
        if valore is not None:
            padre = modello._meta.get_field(nome_campo).related_model
            genitori[(modello, voce.object_pk)] = (padre, valore)
    return genitori


def _assemblea_di(modello, pk: str, genitori: Genitori) -> str | None:
    while modello is not Assemblea:
        genitore = genitori.get((modello, pk))
        if genitore is None:
            return None
        modello, pk = genitore
    return pk


def _testo(campo: models.Field | None, valore) -> str:
    if valore in (NULLO, None):
        return "—"
    if campo is not None and campo.choices:
        scelte = {str(chiave): str(etichetta) for chiave, etichetta in campo.flatchoices}
        return scelte.get(str(valore), str(valore))
    if isinstance(campo, models.BooleanField):
        return {"True": "sì", "False": "no"}.get(str(valore), str(valore))
    try:
        if isinstance(campo, models.DateTimeField):
            # auditlog registra l'ora in UTC, senza fuso.
            istante = datetime.datetime.fromisoformat(str(valore))
            if timezone.is_naive(istante):
                istante = istante.replace(tzinfo=datetime.UTC)
            return f"{timezone.localtime(istante):%d/%m/%Y %H:%M:%S}"
        if isinstance(campo, models.DateField):
            return f"{datetime.date.fromisoformat(str(valore)):%d/%m/%Y}"
    except ValueError:
        pass
    return str(valore)


def _modifiche(modello: type[models.Model], voce: LogEntry) -> list[Modifica]:
    """Solo i campi del modello (non le relazioni inverse che auditlog elenca
    con un segnaposto); alla creazione e all'eliminazione si tralasciano i
    campi vuoti."""
    campi = {f.name: f for f in modello._meta.concrete_fields}
    risultato = []
    for nome, (prima, dopo) in sorted((voce.changes or {}).items()):
        campo = campi.get(nome)
        if campo is None or nome == "id":
            continue
        if voce.action != LogEntry.Action.UPDATE and NULLO in (prima, dopo):
            if (dopo if prima == NULLO else prima) in (NULLO, ""):
                continue
        risultato.append(
            Modifica(str(campo.verbose_name), _testo(campo, prima), _testo(campo, dopo))
        )
    return risultato


def voci(assemblea: Assemblea, tipo: str = "") -> list[Voce]:
    """Le operazioni sull'assemblea, dalla più recente; `tipo` (nome del
    modello) restringe a un tipo di oggetto."""
    per_tipo = {ContentType.objects.get_for_model(m).pk: m for m in MODELLI}
    tutte = list(
        LogEntry.objects.filter(content_type_id__in=per_tipo)
        .select_related("actor")
        .order_by("-timestamp", "-pk")
    )
    genitori = _genitori(tutte, per_tipo)
    risultato = []
    for voce in tutte:
        modello = per_tipo[voce.content_type_id]
        if tipo and modello._meta.model_name != tipo:
            continue
        if _assemblea_di(modello, voce.object_pk, genitori) != str(assemblea.pk):
            continue
        dati = voce.additional_data if isinstance(voce.additional_data, dict) else {}
        risultato.append(
            Voce(
                quando=voce.timestamp,
                autore=str(voce.actor) if voce.actor else (voce.actor_email or "Sistema"),
                eseguito_da_reale=str(dati.get("eseguito_da_reale", "")),
                indirizzo=voce.remote_addr or "",
                azione=AZIONI.get(voce.action, voce.get_action_display()),
                tipo=str(modello._meta.verbose_name).capitalize(),
                oggetto=voce.object_repr,
                modifiche=_modifiche(modello, voce),
            )
        )
    return risultato
