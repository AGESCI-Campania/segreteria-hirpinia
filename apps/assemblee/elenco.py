"""Elenco degli aventi diritto di un'assemblea (D-70): unico punto delle regole.

Le view chiamano solo queste funzioni. L'anagrafica (`CensimentoCapo`) si
legge e basta: nessuna funzione qui scrive su `Capo`, `CensimentoCapo` o
`IncaricoUnita`."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.organizzazione.models import Gruppo

from .models import (
    Assemblea,
    AventeDiritto,
    IncaricoDichiarato,
    MotivoUscita,
    OrigineAvente,
    TipoAssemblea,
)
from .permessi import puo_gestire_assemblee, puo_operare


def _verifica_gestore(utente: Utente) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied("Solo amministratori, segreteria e RdZ modificano l'elenco.")


def _verifica_modificabile(assemblea: Assemblea) -> None:
    if assemblea.conclusa:
        raise ValidationError("L'assemblea è conclusa: l'elenco non è più modificabile.")


# --- Anno dei dati e voto in app ---------------------------------------------


def anno_per_gruppo(assemblea: Assemblea, gruppo: Gruppo) -> int:
    """Anno dei censiti da usare per `gruppo` (D-70). Primaverile: sempre
    l'anno corrente. Autunnale: l'anno corrente se in Catello ci sono già
    censiti di quel gruppo per l'anno corrente (autorizzazioni parziali),
    altrimenti il precedente."""
    if assemblea.tipo == TipoAssemblea.PRIMAVERILE:
        return assemblea.anno_scout
    if CensimentoCapo.objects.filter(anno_scout=assemblea.anno_scout, gruppo=gruppo).exists():
        return assemblea.anno_scout
    return assemblea.anno_scout - 1


def calcola_vota_in_app(avente: AventeDiritto) -> bool:
    """Unico punto della regola (CLAUDE.md § Assemblee): vota nell'app del
    Nazionale chi ha dati da BuonaStrada, cioè chi per codice socio è fra i
    censiti della Zona dell'anno usato per il suo gruppo, e non è passato a
    carta."""
    if avente.voto_cartaceo_il is not None or not avente.codice_socio:
        return False
    return CensimentoCapo.objects.filter(
        anno_scout=avente.anno_censimento, capo_id=avente.codice_socio
    ).exists()


def _aggiorna_voto(avente: AventeDiritto) -> None:
    avente.vota_in_app = calcola_vota_in_app(avente)


# --- Import all'apertura ------------------------------------------------------


def _gruppi_con_censiti(assemblea: Assemblea) -> list[Gruppo]:
    anni = {assemblea.anno_scout}
    if assemblea.tipo == TipoAssemblea.AUTUNNALE:
        anni.add(assemblea.anno_scout - 1)
    codici = (
        CensimentoCapo.objects.filter(anno_scout__in=anni)
        .values_list("gruppo_id", flat=True)
        .distinct()
    )
    return list(Gruppo.objects.filter(pk__in=codici).order_by("nome"))


@transaction.atomic
def importa_elenco(assemblea: Assemblea, utente: Utente) -> int:
    """Import di tutti i censiti (Comitato compreso) all'apertura
    dell'assemblea, con l'anno scelto gruppo per gruppo. Idempotente: un
    codice socio già in elenco non viene duplicato. Restituisce quanti capi
    sono stati aggiunti."""
    _verifica_gestore(utente)
    _verifica_modificabile(assemblea)
    gia_presenti = set(
        assemblea.aventi_diritto.exclude(codice_socio="").values_list("codice_socio", flat=True)
    )
    nuovi = []
    for gruppo in _gruppi_con_censiti(assemblea):
        anno = anno_per_gruppo(assemblea, gruppo)
        censiti = CensimentoCapo.objects.filter(anno_scout=anno, gruppo=gruppo).select_related(
            "capo"
        )
        for censimento in censiti:
            if censimento.capo_id in gia_presenti:
                continue
            gia_presenti.add(censimento.capo_id)
            nuovi.append(
                AventeDiritto(
                    assemblea=assemblea,
                    capo=censimento.capo,
                    codice_socio=censimento.capo_id,
                    nome=censimento.capo.nome,
                    cognome=censimento.capo.cognome,
                    gruppo=gruppo,
                    gruppo_origine=gruppo,
                    origine=OrigineAvente.IMPORT,
                    anno_censimento=anno,
                    # Importato dai censiti di `anno`: per costruzione ha dati
                    # da BuonaStrada (stessa regola di calcola_vota_in_app).
                    vota_in_app=True,
                    creato_da=utente,
                )
            )
    AventeDiritto.objects.bulk_create(nuovi)
    return len(nuovi)


# --- Modifiche manuali --------------------------------------------------------


@transaction.atomic
def elimina(aventi: Iterable[AventeDiritto], utente: Utente) -> int:
    _verifica_gestore(utente)
    ora = timezone.now()
    eliminati = 0
    for avente in aventi:
        _verifica_modificabile(avente.assemblea)
        if avente.eliminato:
            continue
        avente.eliminato_il = ora
        avente.eliminato_da = utente
        avente.uscita = MotivoUscita.ELIMINATO
        avente.save(update_fields=["eliminato_il", "eliminato_da", "uscita"])
        eliminati += 1
    return eliminati


@transaction.atomic
def ripristina(avente: AventeDiritto, utente: Utente) -> None:
    _verifica_gestore(utente)
    _verifica_modificabile(avente.assemblea)
    avente.eliminato_il = None
    avente.eliminato_da = None
    avente.uscita = ""
    avente.save(update_fields=["eliminato_il", "eliminato_da", "uscita"])


@transaction.atomic
def trasferisci(avente: AventeDiritto, gruppo: Gruppo, utente: Utente) -> None:
    """Cambio di gruppo nell'elenco (D-70): il gruppo di origine resta quello
    del censimento (va nel tracciato), il voto in app non cambia."""
    _verifica_gestore(utente)
    _verifica_modificabile(avente.assemblea)
    if avente.gruppo_origine_id is None:
        avente.gruppo_origine = avente.gruppo
    avente.gruppo = gruppo
    avente.save(update_fields=["gruppo", "gruppo_origine"])


@transaction.atomic
def inserisci(
    assemblea: Assemblea,
    utente: Utente,
    *,
    nome: str,
    cognome: str,
    gruppo: Gruppo,
    provenienza: str,
    codice_socio: str = "",
    incarichi: Iterable[dict] = (),
) -> AventeDiritto:
    """Nuovo capo inserito a mano. Se il codice socio è fra i censiti
    dell'anno del gruppo, vota in app (ha dati da BuonaStrada)."""
    _verifica_gestore(utente)
    _verifica_modificabile(assemblea)
    codice_socio = codice_socio.strip()
    if codice_socio and assemblea.aventi_diritto.filter(codice_socio__iexact=codice_socio).exists():
        raise ValidationError(
            {"codice_socio": "Questo codice socio è già nell'elenco dell'assemblea."}
        )
    avente = AventeDiritto(
        assemblea=assemblea,
        codice_socio=codice_socio,
        nome=nome.strip(),
        cognome=cognome.strip(),
        gruppo=gruppo,
        origine=OrigineAvente.MANUALE,
        provenienza=provenienza,
        anno_censimento=anno_per_gruppo(assemblea, gruppo),
        creato_da=utente,
    )
    if codice_socio:
        avente.capo = Capo.objects.filter(pk=codice_socio).first()
    _aggiorna_voto(avente)
    avente.save()
    IncaricoDichiarato.objects.bulk_create(
        IncaricoDichiarato(avente=avente, **dati) for dati in incarichi if dati.get("funzione")
    )
    return avente


@transaction.atomic
def passa_a_carta(avente: AventeDiritto, utente: Utente) -> None:
    """Un votante in app vota su carta (D-70): gestori e operatori, anche
    durante l'assemblea. Toglierlo dall'app nazionale resta a chi la gestisce."""
    if not puo_operare(utente, avente.assemblea):
        raise PermissionDenied
    _verifica_modificabile(avente.assemblea)
    if not avente.vota_in_app:
        raise ValidationError("Questo capo vota già su carta.")
    avente.voto_cartaceo_il = timezone.now()
    avente.voto_cartaceo_da = utente
    _aggiorna_voto(avente)
    avente.save(update_fields=["voto_cartaceo_il", "voto_cartaceo_da", "vota_in_app"])


@transaction.atomic
def annulla_passaggio_a_carta(avente: AventeDiritto, utente: Utente) -> None:
    if not puo_operare(utente, avente.assemblea):
        raise PermissionDenied
    _verifica_modificabile(avente.assemblea)
    avente.voto_cartaceo_il = None
    avente.voto_cartaceo_da = None
    _aggiorna_voto(avente)
    avente.save(update_fields=["voto_cartaceo_il", "voto_cartaceo_da", "vota_in_app"])


# --- Aggiorna gruppo ----------------------------------------------------------


@dataclass
class AnteprimaGruppo:
    """Cosa cambia riallineando un gruppo ai censiti dell'anno corrente."""

    gruppo: Gruppo
    anno: int
    entrano: list[CensimentoCapo] = field(default_factory=list)
    aggiornati: list[AventeDiritto] = field(default_factory=list)
    da_manuale: list[tuple[AventeDiritto, CensimentoCapo]] = field(default_factory=list)
    omonimi: list[tuple[AventeDiritto, CensimentoCapo]] = field(default_factory=list)
    escono: list[AventeDiritto] = field(default_factory=list)
    restano_eliminati: list[AventeDiritto] = field(default_factory=list)

    @property
    def vuota(self) -> bool:
        return not any(
            [
                self.entrano,
                self.aggiornati,
                self.da_manuale,
                self.omonimi,
                self.escono,
            ]
        )


def gruppi_da_aggiornare(assemblea: Assemblea) -> list[Gruppo]:
    """Gruppi di un'autunnale con censiti dell'anno corrente il cui
    riallineamento cambierebbe qualcosa: stessa regola dell'anteprima, così
    un capo che resta legittimamente sui dati dell'anno precedente (es.
    trasferito a mano e non ancora censito) non tiene il gruppo "da
    aggiornare" per sempre."""
    if assemblea.tipo != TipoAssemblea.AUTUNNALE:
        return []
    codici = (
        CensimentoCapo.objects.filter(anno_scout=assemblea.anno_scout)
        .values_list("gruppo_id", flat=True)
        .distinct()
    )
    return [
        gruppo
        for gruppo in Gruppo.objects.filter(pk__in=codici).order_by("nome")
        if not anteprima_aggiorna_gruppo(assemblea, gruppo).vuota
    ]


def _chiave_nome(nome: str, cognome: str) -> tuple[str, str]:
    return (" ".join(cognome.lower().split()), " ".join(nome.lower().split()))


def anteprima_aggiorna_gruppo(assemblea: Assemblea, gruppo: Gruppo) -> AnteprimaGruppo:
    anno = assemblea.anno_scout
    anteprima = AnteprimaGruppo(gruppo=gruppo, anno=anno)
    censiti = {
        c.capo_id: c
        for c in CensimentoCapo.objects.filter(anno_scout=anno, gruppo=gruppo).select_related(
            "capo"
        )
    }
    elenco = list(assemblea.aventi_diritto.all())
    per_codice = {a.codice_socio: a for a in elenco if a.codice_socio}
    manuali_senza_codice = {
        _chiave_nome(a.nome, a.cognome): a
        for a in elenco
        if a.origine == OrigineAvente.MANUALE and not a.codice_socio and not a.eliminato
    }

    for codice, censimento in censiti.items():
        avente = per_codice.get(codice)
        if avente is None:
            omonimo = manuali_senza_codice.get(
                _chiave_nome(censimento.capo.nome, censimento.capo.cognome)
            )
            if omonimo is not None:
                anteprima.omonimi.append((omonimo, censimento))
            else:
                anteprima.entrano.append(censimento)
        elif avente.uscita == MotivoUscita.ELIMINATO:
            # Eliminato a mano: decisione di chi gestisce, il censimento non la ribalta.
            anteprima.restano_eliminati.append(avente)
        elif avente.origine == OrigineAvente.MANUALE:
            anteprima.da_manuale.append((avente, censimento))
        elif (
            avente.anno_censimento != anno
            or avente.uscita == MotivoUscita.NON_CENSITO
            or avente.gruppo_origine_id != gruppo.pk
        ):
            anteprima.aggiornati.append(avente)

    for avente in elenco:
        if (
            avente.origine == OrigineAvente.IMPORT
            and avente.gruppo_origine_id == gruppo.pk
            and avente.gruppo_id == gruppo.pk  # i trasferiti verso altri gruppi restano
            and not avente.eliminato
            and avente.codice_socio not in censiti
        ):
            anteprima.escono.append(avente)
    return anteprima


@transaction.atomic
def applica_aggiorna_gruppo(
    assemblea: Assemblea,
    gruppo: Gruppo,
    utente: Utente,
    *,
    omonimi_confermati: Iterable[int] = (),
) -> AnteprimaGruppo:
    """Riallinea `gruppo` ai censiti dell'anno corrente (D-70). Gli omonimi
    (capo inserito a mano senza codice, stesso nome e cognome di un censito)
    si uniscono solo se confermati; altrimenti il censito entra come nuovo."""
    _verifica_gestore(utente)
    _verifica_modificabile(assemblea)
    anteprima = anteprima_aggiorna_gruppo(assemblea, gruppo)
    confermati = set(omonimi_confermati)
    anno = anteprima.anno
    ora = timezone.now()

    def _come_importato(avente: AventeDiritto, censimento: CensimentoCapo) -> None:
        avente.capo = censimento.capo
        avente.codice_socio = censimento.capo_id
        avente.nome = censimento.capo.nome
        avente.cognome = censimento.capo.cognome
        avente.origine = OrigineAvente.IMPORT
        avente.gruppo_origine = gruppo
        avente.anno_censimento = anno
        avente.eliminato_il = None
        avente.eliminato_da = None
        avente.uscita = ""
        _aggiorna_voto(avente)
        avente.save()

    for avente in anteprima.aggiornati:
        avente.anno_censimento = anno
        if avente.gruppo_origine_id != gruppo.pk:
            # Censito ora in `gruppo` ma importato da un altro: trasferimento
            # rilevato dai dati di BuonaStrada. Il gruppo attuale segue solo se
            # non era già stato trasferito a mano.
            if avente.gruppo_id == avente.gruppo_origine_id:
                avente.gruppo = gruppo
            avente.gruppo_origine = gruppo
        if avente.uscita == MotivoUscita.NON_CENSITO:
            avente.eliminato_il = None
            avente.eliminato_da = None
            avente.uscita = ""
        _aggiorna_voto(avente)
        avente.save()
    for avente, censimento in anteprima.da_manuale:
        _come_importato(avente, censimento)
    entrano = list(anteprima.entrano)
    for avente, censimento in anteprima.omonimi:
        if avente.pk in confermati:
            _come_importato(avente, censimento)
        else:
            entrano.append(censimento)
    for censimento in entrano:
        avente = AventeDiritto(
            assemblea=assemblea,
            capo=censimento.capo,
            codice_socio=censimento.capo_id,
            nome=censimento.capo.nome,
            cognome=censimento.capo.cognome,
            gruppo=gruppo,
            gruppo_origine=gruppo,
            origine=OrigineAvente.IMPORT,
            anno_censimento=anno,
            creato_da=utente,
        )
        _aggiorna_voto(avente)
        avente.save()
    for avente in anteprima.escono:
        avente.eliminato_il = ora
        avente.eliminato_da = utente
        avente.uscita = MotivoUscita.NON_CENSITO
        avente.save(update_fields=["eliminato_il", "eliminato_da", "uscita"])
    return anteprima
