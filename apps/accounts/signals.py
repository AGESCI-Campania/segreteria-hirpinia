from django.dispatch import receiver
from django.utils import timezone
from hijack.signals import hijack_ended, hijack_started

from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail


def _ip_client(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


@receiver(hijack_started)
def registra_inizio_impersonificazione(sender, *, request, hijacker, hijacked, **kwargs):
    from .models import SessioneImpersonificazione

    SessioneImpersonificazione.objects.create(
        amministratore=hijacker,
        utente_impersonato=hijacked,
        ip=_ip_client(request),
    )


@receiver(hijack_ended)
def registra_fine_impersonificazione(sender, *, request, hijacker, hijacked, **kwargs):
    from .models import SessioneImpersonificazione

    sessione = (
        SessioneImpersonificazione.objects.filter(
            amministratore=hijacker, utente_impersonato=hijacked, terminata_il__isnull=True
        )
        .order_by("-iniziata_il")
        .first()
    )
    if sessione is not None:
        sessione.terminata_il = timezone.now()
        sessione.save(update_fields=["terminata_il"])

    # Trasparenza verso l'utente impersonato (D-27), non un requisito tecnico:
    # fail_silently=True perché un fallimento nell'invio non deve interrompere
    # il rilascio della sessione.
    invia_email_template(
        codice_template=CodiceTemplateEmail.FINE_IMPERSONIFICAZIONE,
        destinatari=[hijacked.email],
        contesto={
            "amministratore": str(hijacker),
            "quando": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        },
    )
