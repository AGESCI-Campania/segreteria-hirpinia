"""Elenco degli aventi diritto di un'assemblea (D-70): unico punto delle regole.

Le view chiamano solo queste funzioni. L'anagrafica (`CensimentoCapo`) si
legge e basta: nessuna funzione qui scrive su `Capo`, `CensimentoCapo` o
`IncaricoUnita`."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
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
    Sesso,
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
    """Unico punto della regola (CLAUDE.md § Assemblee). Chi è passato a carta
    vota su carta. Con il voto di Catello vota in app chiunque altro, con il
    codice di voto (deviazione da D-70 dichiarata in docs/plan_voto.md). Con
    l'app del Nazionale vota in app chi ha dati da BuonaStrada, cioè chi per
    codice socio è fra i censiti della Zona dell'anno usato per il suo gruppo."""
    if avente.voto_cartaceo_il is not None:
        return False
    if avente.assemblea.voto_catello:
        return True
    if not avente.codice_socio:
        return False
    return CensimentoCapo.objects.filter(
        anno_scout=avente.anno_censimento, capo_id=avente.codice_socio
    ).exists()


def sesso_da_capo(capo: Capo | None) -> str:
    """Sesso dell'anagrafica, solo se è un valore atteso («M»/«F»): un altro
    valore non si normalizza per somiglianza, resta non noto."""
    if capo is not None and capo.sesso in Sesso.values:
        return capo.sesso
    return ""


def _aggiorna_voto(avente: AventeDiritto) -> None:
    avente.vota_in_app = calcola_vota_in_app(avente)


def ricalcola_voto(assemblea: Assemblea) -> None:
    """Riapplica la regola a tutto l'elenco: serve quando cambia il sistema di
    voto dell'assemblea."""
    for avente in assemblea.aventi_diritto.all():
        nuovo = calcola_vota_in_app(avente)
        if nuovo != avente.vota_in_app:
            avente.vota_in_app = nuovo
            avente.save(update_fields=["vota_in_app"])


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


def _da_censimento(
    assemblea: Assemblea, censimento: CensimentoCapo, anno: int, utente: Utente
) -> AventeDiritto:
    return AventeDiritto(
        assemblea=assemblea,
        capo=censimento.capo,
        codice_socio=censimento.capo_id,
        nome=censimento.capo.nome,
        cognome=censimento.capo.cognome,
        email=censimento.capo.email,
        sesso=sesso_da_capo(censimento.capo),
        gruppo=censimento.gruppo,
        gruppo_origine=censimento.gruppo,
        origine=OrigineAvente.IMPORT,
        anno_censimento=anno,
        # Importato dai censiti di `anno`: per costruzione ha dati da
        # BuonaStrada (stessa regola di calcola_vota_in_app).
        vota_in_app=True,
        creato_da=utente,
    )


def _codici_in_elenco(assemblea: Assemblea) -> set[str]:
    """Codici già nell'elenco, usciti compresi: chi è uscito si ripristina,
    non si reimporta."""
    return set(
        assemblea.aventi_diritto.exclude(codice_socio="").values_list("codice_socio", flat=True)
    )


def _censiti_da_importare(assemblea: Assemblea, gruppo: Gruppo):
    anno = anno_per_gruppo(assemblea, gruppo)
    censiti = CensimentoCapo.objects.filter(anno_scout=anno, gruppo=gruppo).select_related(
        "capo", "gruppo"
    )
    return anno, censiti


@transaction.atomic
def importa_elenco(
    assemblea: Assemblea, utente: Utente, gruppi: Iterable[Gruppo] | None = None
) -> int:
    """Import dei censiti (Comitato compreso), con l'anno scelto gruppo per
    gruppo: all'apertura dell'assemblea, o dopo su un'assemblea nata vuota o
    per un solo gruppo (D19/D21). Idempotente: un codice socio già in elenco,
    anche uscito, non viene duplicato. Restituisce quanti capi sono stati
    aggiunti."""
    _verifica_gestore(utente)
    _verifica_modificabile(assemblea)
    gia_presenti = _codici_in_elenco(assemblea)
    nuovi = []
    for gruppo in _gruppi_con_censiti(assemblea) if gruppi is None else gruppi:
        anno, censiti = _censiti_da_importare(assemblea, gruppo)
        for censimento in censiti:
            if censimento.capo_id in gia_presenti:
                continue
            gia_presenti.add(censimento.capo_id)
            nuovi.append(_da_censimento(assemblea, censimento, anno, utente))
    AventeDiritto.objects.bulk_create(nuovi)
    return len(nuovi)


def gruppi_con_censiti(assemblea: Assemblea) -> list[Gruppo]:
    """Gruppi da cui si può importare (D21)."""
    return _gruppi_con_censiti(assemblea)


def censiti_aggiungibili(assemblea: Assemblea):
    """Censiti che «Aggiungi dall'anagrafica» può proporre (D20): quelli degli
    anni dell'import, con l'anno scelto gruppo per gruppo come all'apertura,
    di tutti i gruppi compreso il Comitato, non ancora nell'elenco."""
    anni = {assemblea.anno_scout}
    if assemblea.tipo == TipoAssemblea.AUTUNNALE:
        anni.add(assemblea.anno_scout - 1)
    anno_del_gruppo = {g.pk: anno_per_gruppo(assemblea, g) for g in _gruppi_con_censiti(assemblea)}
    filtro = Q()
    for codice, anno in anno_del_gruppo.items():
        filtro |= Q(gruppo_id=codice, anno_scout=anno)
    if not filtro:
        return CensimentoCapo.objects.none()
    return (
        CensimentoCapo.objects.filter(filtro)
        .exclude(capo_id__in=_codici_in_elenco(assemblea))
        .select_related("capo", "gruppo")
    )


@transaction.atomic
def aggiungi_da_anagrafica(
    assemblea: Assemblea, codice_socio: str, utente: Utente
) -> AventeDiritto:
    """Un singolo censito nell'elenco (D18/D20), come se fosse stato importato."""
    _verifica_gestore(utente)
    _verifica_modificabile(assemblea)
    censimento = censiti_aggiungibili(assemblea).filter(capo_id=codice_socio).first()
    if censimento is None:
        if assemblea.aventi_diritto.filter(codice_socio=codice_socio).exists():
            raise ValidationError(
                "Il capo è già nell'elenco: se è uscito, ripristinalo dall'elenco."
            )
        raise ValidationError("Il capo non è fra i censiti che si possono importare.")
    avente = _da_censimento(assemblea, censimento, censimento.anno_scout, utente)
    avente.save()
    return avente


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
def ripristina(avente: AventeDiritto, utente: Utente) -> list[Modifica]:
    """Riporta nell'elenco un capo uscito e ne riallinea i dati con
    l'anagrafica (D18). Restituisce le modifiche ai dati."""
    _verifica_gestore(utente)
    _verifica_modificabile(avente.assemblea)
    avente.eliminato_il = None
    avente.eliminato_da = None
    avente.uscita = ""
    avente.save(update_fields=["eliminato_il", "eliminato_da", "uscita"])
    modifiche = modifiche_da_anagrafica(avente)
    _applica_modifiche(avente, modifiche)
    return modifiche


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
    email: str = "",
    sesso: str = "",
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
        email=email.strip(),
        gruppo=gruppo,
        origine=OrigineAvente.MANUALE,
        provenienza=provenienza,
        anno_censimento=anno_per_gruppo(assemblea, gruppo),
        creato_da=utente,
    )
    if sesso and sesso not in Sesso.values:
        raise ValidationError({"sesso": "Sesso non valido."})
    avente.sesso = sesso
    if codice_socio:
        avente.capo = Capo.objects.filter(pk=codice_socio).first()
        if avente.capo and not avente.email:
            avente.email = avente.capo.email
        if avente.capo and not avente.sesso:
            avente.sesso = sesso_da_capo(avente.capo)
    # Indicati a mano qui e diversi dall'anagrafica: valgono come correzioni.
    avente.email_corretta = bool(email.strip()) and (
        avente.capo is None or email.strip().lower() != (avente.capo.email or "").lower()
    )
    avente.sesso_corretto = bool(sesso) and (
        avente.capo is None or sesso != sesso_da_capo(avente.capo)
    )
    _aggiorna_voto(avente)
    avente.save()
    IncaricoDichiarato.objects.bulk_create(
        IncaricoDichiarato(avente=avente, **dati) for dati in incarichi if dati.get("funzione")
    )
    return avente


def normalizza_email(email: str) -> str:
    """Unica validazione dell'email di un avente (form, banco, import Excel):
    spazi tolti, minuscole; ValidationError se non è un indirizzo valido."""
    email = email.strip().lower()
    if email:
        validate_email(email)
    return email


@transaction.atomic
def aggiorna_email(avente: AventeDiritto, email: str, utente: Utente) -> bool:
    """Corregge l'email per l'assemblea (mai quella dell'anagrafica): gestori,
    e operatori al banco. Restituisce False se non cambia nulla."""
    if not puo_operare(utente, avente.assemblea):
        raise PermissionDenied
    _verifica_modificabile(avente.assemblea)
    email = normalizza_email(email)
    if email == avente.email:
        return False
    avente.email = email
    avente.email_corretta = True
    avente.save(update_fields=["email", "email_corretta"])
    return True


@transaction.atomic
def aggiorna_sesso(avente: AventeDiritto, sesso: str, utente: Utente) -> bool:
    """Corregge il sesso per l'assemblea (mai quello dell'anagrafica), come
    l'email: il riallineamento non sovrascrive la correzione (D17).
    Restituisce False se non cambia nulla."""
    if not puo_operare(utente, avente.assemblea):
        raise PermissionDenied
    _verifica_modificabile(avente.assemblea)
    if sesso and sesso not in Sesso.values:
        raise ValidationError("Sesso non valido.")
    if sesso == avente.sesso:
        return False
    avente.sesso = sesso
    avente.sesso_corretto = True
    avente.save(update_fields=["sesso", "sesso_corretto"])
    return True


@transaction.atomic
def passa_a_carta(avente: AventeDiritto, utente: Utente) -> None:
    """Un votante in app vota su carta (D-70): gestori e operatori, anche
    durante l'assemblea. Toglierlo dall'app nazionale resta a chi la gestisce."""
    if not puo_operare(utente, avente.assemblea):
        raise PermissionDenied
    _verifica_modificabile(avente.assemblea)
    if not avente.vota_in_app:
        raise ValidationError("Questo capo vota già su carta.")
    if avente.assemblea.voto_catello:
        # Lazy: apps.voto dipende da questo modulo, non il contrario.
        from apps.voto.codici import verifica_passaggio_a_carta

        verifica_passaggio_a_carta(avente)
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
        # Un'email già corretta per l'assemblea vince su quella dell'anagrafica.
        avente.email = avente.email or censimento.capo.email
        if not avente.sesso_corretto:
            avente.sesso = sesso_da_capo(censimento.capo)
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
            email=censimento.capo.email,
            sesso=sesso_da_capo(censimento.capo),
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


# --- Riallineamento con l'anagrafica ---------------------------------------------
#
# docs/plan_preparazione_assemblea.md, D13-D18: nome, cognome, sesso ed email
# dall'anagrafica, salvo quelli corretti nel modulo; il gruppo del censimento
# dall'anno dei dati dell'avente, senza perdere i trasferimenti fatti a mano.
# Solo capi con codice socio: gli altri non hanno un capo a cui agganciarsi.


@dataclass(frozen=True)
class Modifica:
    campo: str
    etichetta: str
    prima: str
    dopo: str
    valore: object = None


@dataclass
class RigaRiallineamento:
    avente: AventeDiritto
    modifiche: list[Modifica]


def modifiche_da_anagrafica(avente: AventeDiritto) -> list[Modifica]:
    """Cosa cambierebbe nell'avente riallineandolo all'anagrafica. L'anagrafica
    si legge e basta."""
    if not avente.codice_socio:
        return []
    capo = avente.capo or Capo.objects.filter(pk=avente.codice_socio).first()
    if capo is None:
        return []
    modifiche: list[Modifica] = []
    if avente.capo_id is None:
        modifiche.append(Modifica("capo", "Anagrafica", "—", "collegato", capo))
    for campo, etichetta in (("nome", "Nome"), ("cognome", "Cognome")):
        nuovo = getattr(capo, campo)
        if nuovo and nuovo != getattr(avente, campo):
            modifiche.append(Modifica(campo, etichetta, getattr(avente, campo), nuovo, nuovo))
    sesso = sesso_da_capo(capo)
    if not avente.sesso_corretto and sesso and sesso != avente.sesso:
        modifiche.append(Modifica("sesso", "Sesso", avente.sesso or "—", sesso, sesso))
    email = (capo.email or "").strip().lower()
    if not avente.email_corretta and email and email != avente.email.lower():
        modifiche.append(Modifica("email", "Email", avente.email or "—", email, email))
    if avente.origine == OrigineAvente.IMPORT:
        censimento = (
            CensimentoCapo.objects.filter(anno_scout=avente.anno_censimento, capo=capo)
            .select_related("gruppo")
            .first()
        )
        if censimento is not None and censimento.gruppo_id != avente.gruppo_origine_id:
            prima = avente.gruppo_origine.nome if avente.gruppo_origine is not None else "—"
            modifiche.append(
                Modifica("gruppo", "Gruppo", prima, censimento.gruppo.nome, censimento.gruppo)
            )
    return modifiche


def _applica_modifiche(avente: AventeDiritto, modifiche: list[Modifica]) -> None:
    if not modifiche:
        return
    for modifica in modifiche:
        if modifica.campo == "gruppo":
            gruppo = modifica.valore
            assert isinstance(gruppo, Gruppo)
            # Il gruppo attuale segue solo se non era stato trasferito a mano.
            if avente.gruppo_id == avente.gruppo_origine_id:
                avente.gruppo = gruppo
            avente.gruppo_origine = gruppo
        else:
            setattr(avente, modifica.campo, modifica.valore)
    _aggiorna_voto(avente)
    avente.save()


def anteprima_riallinea(assemblea: Assemblea) -> list[RigaRiallineamento]:
    righe = []
    aventi = (
        assemblea.aventi_diritto.nell_elenco()
        .exclude(codice_socio="")
        .select_related("capo", "gruppo", "gruppo_origine")
        .order_by("cognome", "nome")
    )
    for avente in aventi:
        modifiche = modifiche_da_anagrafica(avente)
        if modifiche:
            righe.append(RigaRiallineamento(avente, modifiche))
    return righe


@transaction.atomic
def applica_riallinea(assemblea: Assemblea, utente: Utente) -> int:
    """Ricalcola l'anteprima da zero (mai quella mostrata) e la applica.
    Idempotente. Restituisce quanti capi sono cambiati."""
    _verifica_gestore(utente)
    _verifica_modificabile(assemblea)
    righe = anteprima_riallinea(assemblea)
    for riga in righe:
        _applica_modifiche(riga.avente, riga.modifiche)
    return len(righe)
