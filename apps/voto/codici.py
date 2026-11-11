"""Codici di voto (docs/plan_voto.md, flusso 1): unico punto delle regole.

- 10 caratteri da un alfabeto senza caratteri ambigui (niente 0/O, 1/I/L):
  31 simboli, circa 50 bit. Si mostrano a gruppi (`K7QM-R4XP-2W`) per essere
  copiati a mano; la pagina di voto li accetta anche senza trattini e in
  minuscolo.
- Si salva solo l'hash (HMAC-SHA256 con chiave derivata da SECRET_KEY), come
  l'OTP di attivazione (D-20). Il codice in chiaro esiste solo nel valore
  restituito da `emetti()`: va nell'email o sullo schermo del banco, mai in un
  log, mai nel database.
- Un solo codice attivo per avente e seduta: emetterne uno nuovo revoca il
  precedente.

Le view chiamano solo queste funzioni."""

from __future__ import annotations

import enum
import logging
import secrets

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.accounts.models import Utente
from apps.assemblee import prova
from apps.assemblee.models import AventeDiritto, ModalitaVoto, Seduta
from apps.assemblee.permessi import puo_operare
from apps.core.invio_email import invia_email_template
from apps.core.models import CodiceTemplateEmail

from .models import CodiceVoto

logger = logging.getLogger(__name__)

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LUNGHEZZA = 10
_SALE_HMAC = "apps.voto.codici.CodiceVoto"


def genera() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(LUNGHEZZA))


def normalizza(codice: str) -> str:
    """Toglie spazi e trattini, porta in maiuscolo. Non corregge i caratteri
    esclusi dall'alfabeto: un codice con una O o un 1 non è valido."""
    return "".join(c for c in codice.upper() if c.isalnum())


def formatta(codice: str) -> str:
    codice = normalizza(codice)
    return "-".join(codice[i : i + 4] for i in range(0, len(codice), 4))


def calcola_hash(codice: str) -> str:
    return salted_hmac(_SALE_HMAC, normalizza(codice), algorithm="sha256").hexdigest()


def link_urna(codice: str) -> str:
    """Il codice sta nel fragment (#c=…): il browser non lo manda al server,
    quindi non finisce nei log di accesso."""
    return f"{settings.SITE_URL}{reverse('voto:urna')}#c={normalizza(codice)}"


def codice_attivo(seduta: Seduta, avente: AventeDiritto) -> CodiceVoto | None:
    return CodiceVoto.objects.filter(seduta=seduta, avente=avente, revocato_il__isnull=True).first()


def aventi_con_codice(seduta: Seduta) -> dict[int, CodiceVoto]:
    """Codice attivo per avente, per lo stato al banco (una query)."""
    return {
        c.avente_id: c for c in CodiceVoto.objects.filter(seduta=seduta, revocato_il__isnull=True)
    }


def _verifica_emissione(seduta: Seduta, avente: AventeDiritto, utente: Utente) -> None:
    assemblea = seduta.assemblea
    if not puo_operare(utente, assemblea):
        raise PermissionDenied
    if not assemblea.voto_catello:
        raise ValidationError("Questa assemblea non usa il voto in app.")
    if not seduta.aperta:
        raise ValidationError("La seduta non è aperta.")
    if avente.assemblea_id != assemblea.pk or avente.eliminato:
        raise ValidationError("Questo capo non è nell'elenco degli aventi diritto.")
    if not avente.vota_in_app:
        raise ValidationError(f"{avente} vota su carta: non riceve il codice.")


def _revoca_attivi(seduta: Seduta, avente: AventeDiritto, utente: Utente | None) -> int:
    return CodiceVoto.objects.filter(seduta=seduta, avente=avente, revocato_il__isnull=True).update(
        revocato_il=timezone.now(), revocato_da=utente
    )


@transaction.atomic
def emetti(seduta: Seduta, avente: AventeDiritto, utente: Utente) -> str:
    """Nuovo codice per `avente` nella seduta, revocando quello attivo.
    Restituisce il codice in chiaro: chi chiama lo mostra o lo invia, e poi
    non può più rileggerlo."""
    _verifica_emissione(seduta, avente, utente)
    _revoca_attivi(seduta, avente, utente)
    while True:
        codice = genera()
        hash_codice = calcola_hash(codice)
        if not CodiceVoto.objects.filter(hash=hash_codice).exists():
            break
    CodiceVoto.objects.create(seduta=seduta, avente=avente, hash=hash_codice, emesso_da=utente)
    return codice


class EsitoInvio(enum.Enum):
    INVIATO = "inviato"
    GIA_ATTIVO = "già attivo"
    SENZA_EMAIL = "senza email"
    INVIO_FALLITO = "invio fallito"
    NON_PREVISTO = "non previsto"


def come_votare(seduta: Seduta, codice: str) -> tuple[str, str]:
    """Paragrafo «come votare» dell'email del codice e link all'urna. Con la
    modalità «solo seggi» niente link: dal telefono il codice non funziona, si
    porta al seggio in sala (il link è vuoto anche per un template
    personalizzato che lo usasse)."""
    if seduta.assemblea.modalita_voto == ModalitaVoto.SOLO_SEGGIO:
        return (
            "In questa assemblea si vota solo ai seggi in sala: quando la votazione\n"
            "viene aperta, vai a un seggio e inserisci il codice.",
            "",
        )
    link = link_urna(codice)
    return (
        "Per votare apri questo link quando la votazione viene aperta in sala (il\n"
        f"codice è già inserito):\n{link}\n\n"
        "Puoi anche votare a un seggio in sala, inserendo il codice.",
        link,
    )


def contesto_email(seduta: Seduta, avente: AventeDiritto, codice: str) -> dict[str, str]:
    paragrafo, link = come_votare(seduta, codice)
    return {
        "nome": f"{avente.nome} {avente.cognome}",
        "assemblea": str(seduta.assemblea),
        "codice": formatta(codice),
        "come_votare": paragrafo,
        "link": link,
    }


def invia(seduta: Seduta, avente: AventeDiritto, utente: Utente) -> EsitoInvio:
    """Emette un nuovo codice e lo manda all'email dell'avente. Se l'invio
    fallisce il codice appena emesso si revoca: un codice che nessuno ha
    ricevuto non deve restare valido."""
    if not avente.email:
        return EsitoInvio.SENZA_EMAIL
    codice = emetti(seduta, avente, utente)
    try:
        invia_email_template(
            codice_template=CodiceTemplateEmail.CODICE_VOTO,
            destinatari=[avente.email],
            contesto=contesto_email(seduta, avente, codice),
            fail_silently=False,
            **prova.opzioni_invio(seduta.assemblea, prova.ETICHETTA_CODICE_VOTO),
        )
    except Exception:
        # Mai il codice né l'indirizzo nel log: solo che l'invio non è riuscito.
        logger.exception("Invio del codice di voto fallito (seduta=%s)", seduta.pk)
        _revoca_attivi(seduta, avente, utente)
        return EsitoInvio.INVIO_FALLITO
    CodiceVoto.objects.filter(seduta=seduta, avente=avente, revocato_il__isnull=True).update(
        inviato_per_email=True
    )
    return EsitoInvio.INVIATO


def dopo_la_presenza(seduta: Seduta, avente: AventeDiritto, utente: Utente) -> EsitoInvio:
    """Chiamata dopo `registra_presenza()`: con il voto di Catello chi vota in
    app riceve il codice per email, se non ne ha già uno attivo per la seduta
    (es. rispuntato durante una verifica del quorum)."""
    assemblea = seduta.assemblea
    if not assemblea.voto_catello or not avente.vota_in_app:
        return EsitoInvio.NON_PREVISTO
    if codice_attivo(seduta, avente) is not None:
        return EsitoInvio.GIA_ATTIVO
    return invia(seduta, avente, utente)


def verifica_passaggio_a_carta(avente: AventeDiritto) -> None:
    """Chiamata da `elenco.passa_a_carta()`: rifiuta il passaggio di chi ha già
    votato in app in una votazione non ancora scrutinata (voterebbe due
    volte), poi revoca i codici attivi."""
    from .urna import ha_votato_in_app_in_corso

    if ha_votato_in_app_in_corso(avente):
        raise ValidationError(
            f"{avente} ha già votato in app in una votazione in corso: non può passare a carta."
        )
    CodiceVoto.objects.filter(avente=avente, revocato_il__isnull=True).update(
        revocato_il=timezone.now()
    )


@transaction.atomic
def revoca_tutti(assemblea, utente: Utente | None) -> int:
    """Revoca ogni codice attivo dell'assemblea: serve quando si torna all'app
    del Nazionale prima delle votazioni."""
    return CodiceVoto.objects.filter(seduta__assemblea=assemblea, revocato_il__isnull=True).update(
        revocato_il=timezone.now(), revocato_da=utente
    )
