"""Attivazione tramite OTP (D-20), recupero autonomo (D-25). Unico punto
autorizzato a creare, verificare e far scadere un InvitoAttivazione."""

from dataclasses import dataclass

from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.organizzazione.models import AllowlistGruppo, Gruppo, anno_scout_corrente

from .models import (
    Delega,
    InvitoAttivazione,
    Ruolo,
    StatoInvito,
    StatoUtente,
    TipoUtente,
    Utente,
    genera_codice_otp,
)


class InvitoNonValidoError(Exception):
    """Sollevata per codice errato, scaduto, revocato o inesistente. Il
    messaggio non deve mai distinguere questi casi verso l'utente finale
    (D-20/D-25: niente enumerazione)."""


def crea_invito(
    *,
    email: str,
    creato_da: Utente | None,
    gruppo: Gruppo | None = None,
    ruolo_proposto: str | None = None,
    delega_pendente: Delega | None = None,
) -> InvitoAttivazione:
    """Un nuovo invito per la stessa email revoca il precedente (D-20). La
    scrittura su database è in una propria transazione, separata dall'invio
    dell'email: un fallimento dell'invio (per esempio nel lotto massivo) non
    deve far perdere l'invito già creato, che resta riemettibile."""
    with transaction.atomic():
        InvitoAttivazione.objects.filter(email__iexact=email, stato=StatoInvito.INVIATO).update(
            stato=StatoInvito.REVOCATO
        )

        codice = genera_codice_otp()
        invito = InvitoAttivazione(
            email=email,
            gruppo=gruppo,
            ruolo_proposto=ruolo_proposto or "",
            delega_pendente=delega_pendente,
            creato_da=creato_da,
        )
        invito.imposta_codice(codice)
        invito.save()

    _invia_email_invito(invito, codice)
    return invito


def _invia_email_invito(invito: InvitoAttivazione, codice: str) -> None:
    from django.conf import settings

    corpo = render_to_string(
        "accounts/email/invito_attivazione.txt",
        {"invito": invito, "codice": codice, "site_url": settings.SITE_URL},
    )
    send_mail(
        subject="Catello — attiva il tuo account",
        message=corpo,
        from_email=None,
        recipient_list=[invito.email],
        fail_silently=False,
    )
    invito.inviato_il = timezone.now()
    invito.save(update_fields=["inviato_il"])


def invia_inviti_multipli(
    voci: list[dict], creato_da: Utente
) -> list[tuple[str, bool, str | None]]:
    """Invio massivo (D-20): un fallimento su un destinatario non deve
    interrompere gli altri. Ogni voce è un dict con almeno 'email' e
    opzionalmente 'gruppo'/'ruolo_proposto'. Ritorna (email, esito, errore)."""
    risultati: list[tuple[str, bool, str | None]] = []
    for voce in voci:
        try:
            crea_invito(
                email=voce["email"],
                creato_da=creato_da,
                gruppo=voce.get("gruppo"),
                ruolo_proposto=voce.get("ruolo_proposto"),
            )
            risultati.append((voce["email"], True, None))
        except Exception as exc:  # noqa: BLE001 — un fallimento non ferma il lotto
            risultati.append((voce["email"], False, str(exc)))
    return risultati


@dataclass(frozen=True)
class CandidatoInvito:
    """Voce allowlist invitabile in massa: gruppo attivo, email mai acceduta."""

    voce: AllowlistGruppo
    gruppo: Gruppo


def candidati_invito_massivo(anno: int | None = None) -> list[CandidatoInvito]:
    """Voci allowlist il cui gruppo è attivo per `anno` (default anno corrente,
    D-24: un gruppo disattivato non compare fra i destinatari) e la cui email
    non appartiene a nessun Utente che abbia già effettuato l'accesso."""
    anno = anno if anno is not None else anno_scout_corrente()
    gruppi_attivi = {g.codice: g for g in Gruppo.objects.attivi(anno)}
    email_con_accesso = {
        email.lower()
        for email in Utente.objects.filter(last_login__isnull=False).values_list("email", flat=True)
    }
    candidati = []
    for voce in AllowlistGruppo.objects.order_by("codice_gruppo", "email"):
        gruppo = gruppi_attivi.get(voce.codice_gruppo)
        if gruppo is None or voce.email.lower() in email_con_accesso:
            continue
        candidati.append(CandidatoInvito(voce=voce, gruppo=gruppo))
    return candidati


def _ultimo_invito(email: str, stati: list[str]) -> InvitoAttivazione | None:
    return (
        InvitoAttivazione.objects.filter(email__iexact=email, stato__in=stati)
        .order_by("-id")
        .first()
    )


def verifica_e_completa(*, email: str, codice: str, password: str) -> Utente:
    """Le scritture del percorso di errore (scadenza, tentativi, revoca) sono
    fuori da qualunque transazione più ampia e vanno persistite anche quando
    la funzione termina sollevando InvitoNonValidoError; solo il percorso di
    successo (creazione utente + ruolo + invito USATO) è atomico."""
    invito = _ultimo_invito(email, [StatoInvito.INVIATO, StatoInvito.SCADUTO])
    if invito is None:
        raise InvitoNonValidoError

    invito.aggiorna_stato_se_scaduto()
    if invito.stato != StatoInvito.INVIATO:
        raise InvitoNonValidoError

    if not invito.verifica_codice(codice):
        invito.tentativi += 1
        if invito.tentativi >= InvitoAttivazione.MASSIMO_TENTATIVI:
            invito.stato = StatoInvito.REVOCATO
        invito.save(update_fields=["tentativi", "stato"])
        raise InvitoNonValidoError

    with transaction.atomic():
        utente: Utente
        if invito.delega_pendente_id:
            assert invito.delega_pendente is not None
            utente = invito.delega_pendente.delegato
        else:
            trovato = Utente.objects.filter(email__iexact=invito.email).first()
            utente = (
                trovato
                if trovato is not None
                else Utente(email=invito.email, username=invito.email)
            )

        utente.set_password(password)
        if invito.gruppo_id:
            utente.tipo = TipoUtente.GRUPPO
            utente.gruppo = invito.gruppo
        elif not invito.delega_pendente_id:
            utente.tipo = TipoUtente.PERSONA
        # L'invito implica pre-autorizzazione (D-20): l'account nasce già
        # ATTIVO, saltando l'approvazione della segreteria prevista da D-06.
        utente.stato = StatoUtente.ATTIVO
        utente.full_clean(exclude=["password"])
        utente.save()

        if invito.gruppo_id:
            Ruolo.objects.get_or_create(
                utente=utente,
                tipo=Ruolo.Tipo.CG,
                gruppo_id=invito.gruppo_id,
                defaults={
                    "origine": Ruolo.Origine.AMMINISTRATIVO,
                    "assegnato_da": invito.creato_da,
                },
            )
        elif invito.ruolo_proposto and not invito.delega_pendente_id:
            Ruolo.objects.create(
                utente=utente,
                tipo=invito.ruolo_proposto,
                origine=Ruolo.Origine.AMMINISTRATIVO,
                assegnato_da=invito.creato_da,
            )
            if invito.ruolo_proposto == Ruolo.Tipo.RDZ:
                # D-35: il CG derivato su E9001 segue il possesso di RDZ.
                from .ruoli_derivati import sincronizza_cg_comitato_zona

                sincronizza_cg_comitato_zona(utente=utente)

        invito.stato = StatoInvito.USATO
        invito.usato_il = timezone.now()
        invito.save(update_fields=["stato", "usato_il", "tentativi"])

    return utente


@transaction.atomic
def richiedi_recupero(email: str) -> None:
    """Recupero autonomo di un OTP scaduto (D-25): risposta sempre identica
    verso l'utente (anti-enumerazione), gestita dalla view chiamante. Qui la
    logica interna: emette un nuovo invito solo se ne esiste uno recuperabile
    e il gruppo/ruolo associato è ancora attivo."""
    invito = _ultimo_invito(email, [StatoInvito.INVIATO, StatoInvito.SCADUTO])
    if invito is None:
        return
    invito.aggiorna_stato_se_scaduto()
    if invito.stato not in (StatoInvito.INVIATO, StatoInvito.SCADUTO):
        return

    if invito.gruppo_id is not None:
        assert invito.gruppo is not None
        if not invito.gruppo.e_attivo(anno_scout_corrente()):
            return

    crea_invito(
        email=invito.email,
        creato_da=invito.creato_da,
        gruppo=invito.gruppo,
        ruolo_proposto=invito.ruolo_proposto,
        delega_pendente=invito.delega_pendente,
    )
