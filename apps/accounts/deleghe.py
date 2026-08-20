"""Delega a iniziativa del titolare del ruolo (D-04, D-26). Unico punto
autorizzato a creare e revocare deleghe: nessuna view deve manipolare `Delega`
direttamente."""

from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string

from .models import Delega, Ruolo, StatoUtente, TipoUtente, Utente


def _notifica(destinatario_email: str, oggetto: str, template: str, contesto: dict) -> None:
    send_mail(
        subject=oggetto,
        message=render_to_string(template, contesto),
        from_email=None,
        recipient_list=[destinatario_email],
        fail_silently=True,
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
        _notifica(
            delegante.email,
            "Catello — hai concesso una delega",
            "accounts/email/delega_creata.txt",
            {"delega": delega},
        )
    return delega


@transaction.atomic
def revoca_delega(delega: Delega, revocata_da: Utente) -> None:
    delega.attiva = False
    delega.save(update_fields=["attiva"])
    _notifica(
        delega.delegante.email,
        "Catello — una tua delega è stata revocata",
        "accounts/email/delega_revocata.txt",
        {"delega": delega, "revocata_da": revocata_da},
    )


@transaction.atomic
def revoca_deleghe_di_ruolo(ruolo: Ruolo) -> int:
    """Revoca a cascata (esplicita) tutte le deleghe attive di un ruolo, da
    chiamare nella stessa transazione di chi revoca o chiude il ruolo. Copre la
    revoca anticipata; la scadenza naturale per data è già gestita "lazy" da
    `permessi.ruoli_effettivi()`, senza bisogno di questa funzione."""
    deleghe = list(Delega.objects.filter(ruolo=ruolo, attiva=True))
    Delega.objects.filter(ruolo=ruolo, attiva=True).update(attiva=False)
    for delega in deleghe:
        _notifica(
            delega.delegante.email,
            "Catello — una tua delega è stata revocata",
            "accounts/email/delega_revocata.txt",
            {"delega": delega, "revocata_da": None},
        )
    return len(deleghe)
