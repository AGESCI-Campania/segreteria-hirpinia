"""Urna elettronica (docs/plan_voto.md, flusso 2): `vota()` è l'unico punto in
cui si vota. Con più urne aperte insieme nella stessa seduta l'elettore le
vota tutte in un passaggio (`vota_insieme()`, che chiama `vota()` per
ciascuna).

Un codice è accettato solo se è attivo e della seduta, la votazione è aperta
in app, l'avente è fra i presenti dell'ultimo appello valido
(`quorum.presenti()`, non riscritto qui), non è passato a carta e non ha già
votato. Con una delega registrata nella seduta il delegato esprime anche la
scheda dell'AE che l'ha delegato: al massimo due schede (art. 5).

Scheda e votante nascono nella stessa transazione ma senza alcun legame nel
modello; la traccia fisica (ordine, xmin) la cancella il rimescolamento alla
chiusura (scrutinio.py). Nessun log qui registra codici, ricevute o scelte."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.assemblee import quorum
from apps.assemblee.models import (
    AventeDiritto,
    CanaleVoto,
    ModalitaVoto,
    Seduta,
    Sesso,
    TipoVotazione,
    Votazione,
)
from apps.assemblee.votazioni import canali

from . import codici
from .models import CodiceVoto, Postazione, Scheda, Votante

ESITO_VOTO = "VOTO"
ESITO_BIANCA = "BIANCA"
ESITO_NULLA = "NULLA"
ESITI = (ESITO_VOTO, ESITO_BIANCA, ESITO_NULLA)
LUNGHEZZA_NOME_LIBERO = 100
LUNGHEZZA_RICEVUTA = 12


@dataclass(frozen=True)
class Scelte:
    """Cosa esprime una scheda: candidati (id) e nomi liberi, oppure bianca o nulla."""

    esito: str = ESITO_VOTO
    candidati: tuple[int, ...] = ()
    liberi: tuple[str, ...] = ()
    # Con le quote per sesso: il sesso dichiarato per ciascun nome scritto,
    # nello stesso ordine di `liberi` (docs/plan_preparazione_assemblea.md, D2).
    sessi_liberi: tuple[str, ...] = ()

    def come_json(self) -> dict:
        dati = {"esito": self.esito, "candidati": list(self.candidati), "liberi": list(self.liberi)}
        if self.sessi_liberi:
            dati["sessi_liberi"] = list(self.sessi_liberi)
        return dati


@dataclass
class SchedaDaEsprimere:
    """Una scheda che spetta al titolare del codice: la sua, o quella dell'AE
    che l'ha delegato."""

    avente: AventeDiritto
    tramite: AventeDiritto | None = None

    @property
    def per_delega(self) -> bool:
        return self.tramite is not None


@dataclass
class Ricevuta:
    ricevuta: str
    scelte: Scelte
    per_delega_di: AventeDiritto | None = None


@dataclass
class EsitoVoto:
    ricevute: list[Ricevuta] = field(default_factory=list)


def votazioni_in_app(votazione: Votazione) -> bool:
    """Solo elezioni e ballottaggi si votano in app (le palesi per alzata di
    mano, la revoca del mandato resta su carta): decide `canali()`."""
    return votazione.tipo in (
        TipoVotazione.ELEZIONE,
        TipoVotazione.BALLOTTAGGIO,
    ) and CanaleVoto.APP in canali(votazione)


def votazioni_aperte(seduta: Seduta) -> list[Votazione]:
    """Le votazioni con l'urna aperta nella seduta: possono essere più d'una
    (si votano insieme, `vota_insieme()`), nell'ordine di apertura."""
    return list(
        seduta.votazioni.filter(
            aperta_in_app_il__isnull=False, chiusa_in_app_il__isnull=True, chiusa_il__isnull=True
        ).order_by("aperta_in_app_il", "pk")
    )


def chiave_votazioni(votazioni: list[Votazione]) -> str:
    """Identifica l'insieme delle urne aperte: se cambia (se ne apre o chiude
    una) la scheda dell'elettore va ricaricata."""
    return ",".join(str(v.pk) for v in votazioni)


def accedi(codice_in_chiaro: str) -> CodiceVoto | None:
    """Il codice digitato o arrivato dal link, se utilizzabile adesso."""
    codice = (
        CodiceVoto.objects.filter(
            hash=codici.calcola_hash(codice_in_chiaro), revocato_il__isnull=True
        )
        .select_related("seduta__assemblea", "avente")
        .first()
    )
    return codice if codice_valido(codice) else None


def codice_valido(codice: CodiceVoto | None) -> bool:
    """Codice utilizzabile in questo momento (per l'accesso alla pagina di voto)."""
    return (
        codice is not None
        and codice.attivo
        and codice.seduta.aperta
        and codice.seduta.assemblea.voto_catello
        and not codice.avente.eliminato
    )


def schede_spettanti(codice: CodiceVoto, votazione: Votazione) -> list[SchedaDaEsprimere]:
    """Le schede che il titolare del codice può ancora esprimere in
    `votazione`: la propria e, con una delega registrata, quella del delegante.
    Vuota se ha già votato o non può votare in app."""
    avente = codice.avente
    seduta = codice.seduta
    if not avente.vota_in_app:
        return []
    presenti = quorum.presenti(seduta)
    if not presenti.filter(pk=avente.pk).exists():
        return []
    gia = set(Votante.objects.filter(votazione=votazione).values_list("avente_id", flat=True))
    schede = []
    if avente.pk not in gia:
        schede.append(SchedaDaEsprimere(avente=avente))
    delega = seduta.deleghe.filter(delegato=avente).select_related("delegante").first()
    if delega is not None:
        delegante = delega.delegante
        if delegante.vota_in_app and not delegante.eliminato and delegante.pk not in gia:
            schede.append(SchedaDaEsprimere(avente=delegante, tramite=avente))
    return schede


def valida_scelte(votazione: Votazione, scelte: Scelte) -> Scelte:
    """Fino a N preferenze (N = posti), contando anche i nomi liberi; bianca e
    nulla senza preferenze. Restituisce le scelte normalizzate."""
    if scelte.esito not in ESITI:
        raise ValidationError("Scelta non valida.")
    if scelte.esito != ESITO_VOTO:
        return Scelte(esito=scelte.esito)
    if votazione.tipo == TipoVotazione.BALLOTTAGGIO and any(n.strip() for n in scelte.liberi):
        # Il ballottaggio è fra i due candidati proposti (art. 18 c.3): un nome
        # scritto non può essere né l'uno né l'altro.
        raise ValidationError("Nel ballottaggio si sceglie solo fra i due candidati.")
    sessi_candidati = dict(votazione.candidati.values_list("pk", "sesso"))
    candidati = tuple(dict.fromkeys(scelte.candidati))
    if set(candidati) - set(sessi_candidati):
        raise ValidationError("Candidato non valido per questa votazione.")
    quote = votazione.posti_maschili > 0 or votazione.posti_femminili > 0
    liberi: list[str] = []
    sessi_liberi: list[str] = []
    sessi = list(scelte.sessi_liberi) + [""] * (len(scelte.liberi) - len(scelte.sessi_liberi))
    for nome, sesso in zip(scelte.liberi, sessi, strict=False):
        nome = " ".join(str(nome).split())
        if not nome:
            continue
        if len(nome) > LUNGHEZZA_NOME_LIBERO:
            raise ValidationError(
                f"Un nome scritto può avere al massimo {LUNGHEZZA_NOME_LIBERO} caratteri."
            )
        if quote and sesso not in Sesso.values:
            raise ValidationError(f"Indica se «{nome}» è per un posto maschile o femminile.")
        if nome.casefold() not in (n.casefold() for n in liberi):
            liberi.append(nome)
            sessi_liberi.append(sesso if quote else "")
    preferenze = len(candidati) + len(liberi)
    if preferenze == 0:
        raise ValidationError(
            "Scegli almeno un candidato o scrivi un nome, oppure lascia la scheda bianca."
        )
    if preferenze > votazione.posti:
        raise ValidationError(
            f"Puoi esprimere al massimo {votazione.posti} "
            f"{'preferenza' if votazione.posti == 1 else 'preferenze'}."
        )
    if quote:
        _verifica_quote(votazione, [sessi_candidati[c] for c in candidati] + sessi_liberi)
    return Scelte(
        esito=ESITO_VOTO,
        candidati=candidati,
        liberi=tuple(liberi),
        sessi_liberi=tuple(sessi_liberi) if quote else (),
    )


def _verifica_quote(votazione: Votazione, sessi: list[str]) -> None:
    """Per ciascun sesso al massimo i posti di quel sesso più gli
    indifferenti (D4-bis)."""
    indifferenti = votazione.posti - votazione.posti_maschili - votazione.posti_femminili
    for sesso, posti, singolare, plurale in (
        (Sesso.MASCHILE, votazione.posti_maschili, "preferenza maschile", "preferenze maschili"),
        (
            Sesso.FEMMINILE,
            votazione.posti_femminili,
            "preferenza femminile",
            "preferenze femminili",
        ),
    ):
        massimo = posti + indifferenti
        if sessi.count(sesso) > massimo:
            raise ValidationError(
                f"Puoi esprimere al massimo {massimo} {singolare if massimo == 1 else plurale}."
            )


def _nuova_ricevuta() -> str:
    while True:
        grezza = "".join(secrets.choice(codici.ALFABETO) for _ in range(LUNGHEZZA_RICEVUTA))
        ricevuta = codici.formatta(grezza)
        if not Scheda.objects.filter(ricevuta=ricevuta).exists():
            return ricevuta


def ammesso_da(codice: CodiceVoto, postazione: Postazione | None) -> bool:
    """Con «solo seggi» si vota solo da una postazione attiva della seduta del
    codice; altrimenti anche dal proprio dispositivo."""
    if postazione is not None:
        return postazione.attiva and postazione.seduta_id == codice.seduta_id
    return codice.seduta.assemblea.modalita_voto != ModalitaVoto.SOLO_SEGGIO


@transaction.atomic
def vota(
    codice_id: int,
    votazione: Votazione,
    scelte: list[Scelte],
    postazione: Postazione | None = None,
) -> EsitoVoto:
    """Registra le schede del titolare del codice in `votazione`. `codice_id`
    viene dalla sessione aperta con `accedi()` (il codice in chiaro non si
    conserva da nessuna parte); `scelte` ha una voce per ciascuna scheda
    spettante (`schede_spettanti()`), nello stesso ordine: la propria, poi
    quella per delega. Il lock sul codice serializza i doppi invii."""
    codice = (
        CodiceVoto.objects.select_for_update()
        .select_related("seduta__assemblea", "avente")
        .filter(pk=codice_id)
        .first()
    )
    if not codice_valido(codice):
        raise ValidationError("Codice non valido o non più attivo.")
    assert codice is not None
    if not ammesso_da(codice, postazione):
        raise ValidationError("In questa assemblea si vota solo ai seggi.")
    votazione = Votazione.objects.select_for_update().get(pk=votazione.pk)
    if votazione.seduta_id != codice.seduta_id:
        raise ValidationError("Il codice non vale per questa votazione.")
    if not votazioni_in_app(votazione) or not votazione.urna_aperta:
        raise ValidationError("La votazione non è aperta.")
    if not codice.avente.vota_in_app:
        raise ValidationError("Voti su carta: chiedi la scheda al banco.")
    if not quorum.presenti(codice.seduta).filter(pk=codice.avente_id).exists():
        raise ValidationError("Non risulti fra i presenti: passa dal banco.")
    spettanti = schede_spettanti(codice, votazione)
    if not spettanti:
        raise ValidationError("Hai già votato in questa votazione.")
    if len(scelte) != len(spettanti):
        raise ValidationError("Le schede inviate non corrispondono a quelle che ti spettano.")
    validate = [valida_scelte(votazione, s) for s in scelte]
    esito = EsitoVoto()
    for scheda, scelta in zip(spettanti, validate, strict=True):
        Votante.objects.create(votazione=votazione, avente=scheda.avente, tramite=scheda.tramite)
        ricevuta = _nuova_ricevuta()
        Scheda.objects.create(votazione=votazione, ricevuta=ricevuta, scelte=scelta.come_json())
        esito.ricevute.append(
            Ricevuta(
                ricevuta=ricevuta,
                scelte=scelta,
                per_delega_di=scheda.avente if scheda.per_delega else None,
            )
        )
    return esito


def da_votare(codice: CodiceVoto) -> list[tuple[Votazione, list[SchedaDaEsprimere]]]:
    """Le urne aperte in cui il titolare del codice ha ancora schede da
    esprimere, con le schede spettanti in ciascuna."""
    risultato = []
    for votazione in votazioni_aperte(codice.seduta):
        if not votazioni_in_app(votazione):
            continue
        spettanti = schede_spettanti(codice, votazione)
        if spettanti:
            risultato.append((votazione, spettanti))
    return risultato


@transaction.atomic
def vota_insieme(
    codice_id: int,
    scelte: dict[int, list[Scelte]],
    postazione: Postazione | None = None,
) -> list[tuple[Votazione, EsitoVoto]]:
    """Tutte le urne aperte da votare in un solo passaggio: `scelte` ha una
    voce per ogni votazione di `da_votare()` (chiave: id della votazione),
    nessuna esclusa. Ogni votazione passa da `vota()`, unico punto delle
    regole; o si registrano tutte o nessuna."""
    codice = (
        CodiceVoto.objects.select_for_update()
        .select_related("seduta__assemblea", "avente")
        .filter(pk=codice_id)
        .first()
    )
    if not codice_valido(codice):
        raise ValidationError("Codice non valido o non più attivo.")
    assert codice is not None
    attese = [votazione for votazione, _ in da_votare(codice)]
    if not attese:
        raise ValidationError("Non ci sono votazioni da votare.")
    if {v.pk for v in attese} != set(scelte):
        raise ValidationError("Le votazioni aperte sono cambiate: ricontrolla la scheda.")
    return [(v, vota(codice_id, v, scelte[v.pk], postazione)) for v in attese]


def ha_votato_in_app_in_corso(avente: AventeDiritto) -> bool:
    """Per il passaggio a carta: ha già una scheda in app in una votazione non
    ancora scrutinata."""
    return Votante.objects.filter(avente=avente, votazione__chiusa_il__isnull=True).exists()
