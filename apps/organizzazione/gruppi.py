"""Ciclo di vita del gruppo da interfaccia (D-24): disattivazione,
riattivazione, creazione di un nuovo gruppo. Nessuna dipendenza da
`apps.contributi` in questo modulo — è `apps.contributi` a reagire alla
disattivazione via segnale (`apps/contributi/disattivazione_gruppo.py`),
mai il contrario (`organizzazione` è la base della catena di dipendenze,
§4 del documento di progettazione)."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import ruoli_effettivi

from .models import AllowlistGruppo, Gruppo, Origine, StatoGruppoAnno, anno_scout_corrente

RUOLI_GESTIONE_GRUPPI = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


def _verifica_ruolo_gestione_gruppi(utente: Utente) -> None:
    ruoli = ruoli_effettivi(utente)
    if not any(r.tipo in RUOLI_GESTIONE_GRUPPI for r in ruoli):
        raise PermissionDenied(f"{utente}: azione riservata a SEGRETERIA/ADMIN/RDZ.")


def verifica_ruolo_gestione_dati_gruppo(utente: Utente, gruppo: Gruppo) -> None:
    """Perimetro di `modifica_dati_gruppo` (D-35 chiude il caso limite: un CG
    ha al più un gruppo reale, quindi qui il controllo è deterministico)."""
    ruoli = ruoli_effettivi(utente)
    if any(r.tipo in RUOLI_GESTIONE_GRUPPI for r in ruoli):
        return
    if any(
        r.tipo == Ruolo.Tipo.CG and r.gruppo and r.gruppo.codice == gruppo.codice for r in ruoli
    ):
        return
    raise PermissionDenied(
        f"{utente}: azione riservata a SEGRETERIA/ADMIN/RDZ o al capogruppo di {gruppo.codice}."
    )


def crea_gruppo(*, utente: Utente, codice: str, nome: str, email_istituzionale: str) -> Gruppo:
    _verifica_ruolo_gestione_gruppi(utente)
    if not email_istituzionale.strip():
        raise ValidationError(
            "L'email istituzionale è obbligatoria: alimenta l'allowlist per l'invito OTP (D-06)."
        )
    if Gruppo.objects.filter(pk=codice).exists():
        raise ValidationError(
            f"{codice}: esiste già un gruppo con questo codice. Se è disattivato, "
            "usa la riattivazione invece di crearne uno nuovo (D-24)."
        )
    gruppo = Gruppo(
        codice=codice,
        nome=nome,
        email_istituzionale=email_istituzionale,
        origine=Origine.MANUALE,
    )
    gruppo.full_clean()
    gruppo.save()
    # D-24/D-06: alimenta l'allowlist, altrimenti l'account funzionale non
    # potrebbe mai registrarsi né ricevere l'invito con OTP.
    if not AllowlistGruppo.objects.filter(email__iexact=email_istituzionale).exists():
        AllowlistGruppo.objects.create(
            codice_gruppo=codice,
            email=email_istituzionale,
            origine=Origine.MANUALE,
            creata_da=utente,
        )
    return gruppo


def disattiva_gruppo(*, utente: Utente, gruppo: Gruppo, motivo: str) -> StatoGruppoAnno:
    """A-6: la disattivazione vale per l'intero anno associativo *in corso*
    (mai per un anno passato o futuro a scelta) e si propaga agli anni
    successivi finché non viene disposto un nuovo stato."""
    _verifica_ruolo_gestione_gruppi(utente)
    if not motivo.strip():
        raise ValidationError("La disattivazione richiede una motivazione obbligatoria (D-24).")

    anno = anno_scout_corrente()
    if StatoGruppoAnno.objects.filter(gruppo=gruppo, anno_scout=anno).exists():
        raise ValidationError(f"Esiste già una disposizione per {gruppo.codice} nell'anno {anno}.")

    stato = StatoGruppoAnno(
        gruppo=gruppo, anno_scout=anno, attivo=False, motivo=motivo, disposto_da=utente
    )
    stato.full_clean()
    stato.save()
    return stato


def riattiva_gruppo(
    *, utente: Utente, gruppo: Gruppo, anno_scout: int, motivo: str
) -> StatoGruppoAnno:
    """D-24: non è possibile riattivare un gruppo nello stesso anno in cui è
    stato disattivato — al più presto per l'anno successivo, anche in corso
    d'anno."""
    _verifica_ruolo_gestione_gruppi(utente)
    if not motivo.strip():
        raise ValidationError("La riattivazione richiede una motivazione obbligatoria (D-24).")

    ultimo = gruppo.stati_annuali.order_by("-anno_scout").first()
    if ultimo is not None and not ultimo.attivo and anno_scout <= ultimo.anno_scout:
        raise ValidationError(
            f"{gruppo.codice} è stato disattivato per l'anno {ultimo.anno_scout}: la "
            f"riattivazione può valere al più presto dall'anno {ultimo.anno_scout + 1}."
        )
    if StatoGruppoAnno.objects.filter(gruppo=gruppo, anno_scout=anno_scout).exists():
        raise ValidationError(
            f"Esiste già una disposizione per {gruppo.codice} nell'anno {anno_scout}."
        )

    stato = StatoGruppoAnno(
        gruppo=gruppo, anno_scout=anno_scout, attivo=True, motivo=motivo, disposto_da=utente
    )
    stato.full_clean()
    stato.save()
    return stato


def modifica_dati_gruppo(
    *,
    utente: Utente,
    gruppo: Gruppo,
    email_alternativa: str,
    indirizzo: str,
    civico: str,
    cap: str,
    comune: str,
    provincia: str,
    codice_fiscale: str,
    iban: str,
    intestazione_conto: str,
) -> Gruppo:
    """Dati modificabili da "Gestione gruppo": mai `email_istituzionale`, che
    arriva solo da import e non è mai parametro di questa funzione. `iban`/
    `intestazione_conto`: dato bancario sensibile, mai loggato né incluso in
    messaggi di errore (CLAUDE.md) — la validazione del formato IBAN avviene
    nel form (`GruppoModificaForm.clean_iban`), che intercetta e sanifica
    l'errore di `valida_iban()` prima che arrivi qui."""
    verifica_ruolo_gestione_dati_gruppo(utente, gruppo)

    gruppo.email_alternativa = email_alternativa
    gruppo.indirizzo = indirizzo
    gruppo.civico = civico
    gruppo.cap = cap
    gruppo.comune = comune
    gruppo.provincia = provincia
    gruppo.codice_fiscale = codice_fiscale
    gruppo.iban = iban
    gruppo.intestazione_conto = intestazione_conto
    gruppo.full_clean()
    gruppo.save(
        update_fields=[
            "email_alternativa",
            "indirizzo",
            "civico",
            "cap",
            "comune",
            "iban",
            "intestazione_conto",
            "provincia",
            "codice_fiscale",
        ]
    )
    return gruppo
