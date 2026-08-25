"""Delega a iniziativa del titolare del ruolo (D-04, D-26). Unico punto
autorizzato a creare e revocare deleghe: nessuna view deve manipolare `Delega`
direttamente."""

from django.db import transaction

from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail

from .models import Delega, Ruolo, StatoUtente, TipoUtente, Utente


def _notifica_delega_creata(delega: Delega) -> None:
    invia_email_template(
        codice_template=CodiceTemplateEmail.DELEGA_CREATA,
        destinatari=[delega.delegante.email],
        contesto={
            "ruolo": str(delega.ruolo),
            "delegato": str(delega.delegato),
            "scadenza": delega.data_fine.strftime("%d/%m/%Y"),
        },
    )


def _notifica_delega_revocata(delega: Delega, revocata_da: Utente | None) -> None:
    invia_email_template(
        codice_template=CodiceTemplateEmail.DELEGA_REVOCATA,
        destinatari=[delega.delegante.email],
        contesto={
            "ruolo": str(delega.ruolo),
            "delegato": str(delega.delegato),
            "revocata_da_frase": f" da {revocata_da}" if revocata_da else "",
        },
    )


@transaction.atomic
def crea_delega(
    *, delegante: Utente, ruolo: Ruolo, email_delegato: str, data_fine, note: str = ""
) -> Delega:
    """Crea una delega. Se l'email non corrisponde a un utente esistente, crea
    un account PERSONA in stato IN_ATTESA con password inutilizzabile e invia
    un InvitoAttivazione (D-20): l'account non è utilizzabile finché la persona
    non imposta una password, quindi la delega non è esercitabile prima
    dell'attivazione, pur essendo già "attiva" in senso amministrativo (non
    revocata)."""
    delegato = Utente.objects.filter(email__iexact=email_delegato).first()
    nuovo_delegato = delegato is None
    if nuovo_delegato:
        delegato = Utente(
            email=email_delegato,
            username=email_delegato,
            tipo=TipoUtente.PERSONA,
            stato=StatoUtente.IN_ATTESA,
        )
        delegato.set_unusable_password()
        delegato.full_clean(exclude=["password"])
        delegato.save()

    delega = Delega(
        delegante=delegante,
        delegato=delegato,
        ruolo=ruolo,
        attiva=True,
        data_fine=data_fine,
        note=note,
    )
    delega.full_clean()
    delega.save()

    if nuovo_delegato:
        from .inviti import crea_invito

        crea_invito(email=email_delegato, creato_da=delegante, delega_pendente=delega)
    else:
        _notifica_delega_creata(delega)
    return delega


@transaction.atomic
def revoca_delega(delega: Delega, revocata_da: Utente) -> None:
    delega.attiva = False
    delega.save(update_fields=["attiva"])
    _notifica_delega_revocata(delega, revocata_da)


@transaction.atomic
def revoca_deleghe_di_ruolo(ruolo: Ruolo) -> int:
    """Revoca a cascata (esplicita) tutte le deleghe attive di un ruolo, da
    chiamare nella stessa transazione di chi revoca o chiude il ruolo. Copre la
    revoca anticipata; la scadenza naturale per data è già gestita "lazy" da
    `permessi.ruoli_effettivi()`, senza bisogno di questa funzione."""
    deleghe = list(Delega.objects.filter(ruolo=ruolo, attiva=True))
    Delega.objects.filter(ruolo=ruolo, attiva=True).update(attiva=False)
    for delega in deleghe:
        _notifica_delega_revocata(delega, None)
    return len(deleghe)
