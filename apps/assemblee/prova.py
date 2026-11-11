"""Assemblee di prova (docs/plan_preparazione_assemblea.md, D22): le uniche
che si possono eliminare del tutto. Un'assemblea vera non si cancella
dall'interfaccia, e `di_prova` si sceglie solo alla creazione: non si può
rendere eliminabile un'assemblea vera cambiando il flag."""

from __future__ import annotations

import re
from dataclasses import replace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import ALFABETO_OTP, Utente
from apps.core.email import mailpit_api

from .models import Assemblea
from .permessi import puo_gestire_assemblee

ETICHETTA_CODICE_VOTO = "codice-voto"
ETICHETTA_INVITO = "invito"


def etichetta(assemblea: Assemblea) -> str:
    """Etichetta (tag di Mailpit) delle email di un'assemblea di prova."""
    return f"catello-assemblea-{assemblea.pk}"


def opzioni_invio(assemblea: Assemblea, tipo: str) -> dict:
    """Argomenti per `invia_email_template()`/`crea_invito()` di un'email
    legata all'assemblea: «solo Mailpit» per le assemblee di prova che lo
    chiedono (D26), altrimenti nulla."""
    if not assemblea.email_solo_mailpit:
        return {}
    return {"solo_mailpit": True, "etichette": (etichetta(assemblea), tipo)}


@transaction.atomic
def imposta_email_solo_mailpit(assemblea: Assemblea, valore: bool, utente: Utente) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if valore and not assemblea.di_prova:
        raise ValidationError("Solo un'assemblea di prova può mandare le email su Mailpit.")
    assemblea.email_solo_mailpit = valore
    assemblea.save(update_fields=["email_solo_mailpit"])


@transaction.atomic
def elimina(assemblea: Assemblea, utente: Utente) -> None:
    """Elimina l'assemblea di prova con tutto ciò che contiene (elenco, sedute,
    votazioni, schede, codici, seggi, verbali). Gli account creati per il
    comitato elettorale restano: sono account reali."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if not assemblea.di_prova:
        raise ValidationError("Solo un'assemblea di prova si può eliminare.")
    # Lazy: apps.voto dipende da apps.assemblee, non il contrario.
    from apps.voto.models import InterpretazioneNome

    # L'interpretazione di un nome scritto protegge l'avente a cui è
    # attribuita: va tolta prima, altrimenti la cascata si ferma.
    InterpretazioneNome.objects.filter(votazione__seduta__assemblea=assemblea).delete()
    assemblea.delete()


# Codice di attivazione nel testo di un invito: 8 caratteri dell'alfabeto
# dell'OTP (D-20), isolati. Una parola che ci somiglia viene oscurata anche
# lei: meglio un falso positivo che un codice visibile.
_CODICE_INVITO = re.compile(rf"(?<![A-Z0-9])[{re.escape(ALFABETO_OTP)}]{{8}}(?![A-Z0-9])")


def email_su_mailpit(assemblea: Assemblea, utente: Utente) -> list[mailpit_api.Messaggio]:
    """Le email di un'assemblea di prova finite su Mailpit (D28), solo per i
    gestori. Negli inviti di attivazione il codice è oscurato: gli account
    sono reali (D29). I codici di voto di prova restano visibili per provare
    l'urna (deviazione dichiarata da D-71, solo per le assemblee di prova).
    Solleva `mailpit_api.MailpitNonRaggiungibile` se Mailpit non risponde."""
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied
    if not assemblea.di_prova:
        raise ValidationError("Solo per le assemblee di prova.")
    messaggi = mailpit_api.messaggi_con_etichetta(etichetta(assemblea))
    return [
        (
            replace(m, testo=_CODICE_INVITO.sub("••••••••", m.testo))
            if ETICHETTA_INVITO in m.etichette
            else m
        )
        for m in messaggi
    ]
