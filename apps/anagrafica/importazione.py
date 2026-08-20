"""Import CSV Buona Caccia (§6.1, D-22, D-29, D-34): unico punto autorizzato a
scrivere Capo/CensimentoCapo/TrasferimentoCapo/Gruppo/AllowlistGruppo a partire
dal CSV anagrafico. View e comando di gestione chiamano solo `costruisci_piano`
e `applica_piano`, mai i modelli direttamente."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import Ruolo, Utente
from apps.organizzazione.models import AllowlistGruppo, Gruppo
from apps.organizzazione.models import Origine as OrigineGruppo

from .models import Capo, CensimentoCapo, ImportazioneCSV, TrasferimentoCapo
from .parser.buonacaccia import AVVISO, ERRORE, AnomaliaRiga, RisultatoParsing

RUOLI_IMPORT_ANAGRAFICA = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


@dataclass
class OperazioneGruppo:
    ordinale: str
    defaults: dict


@dataclass
class OperazioneCapo:
    codice_socio: str
    defaults: dict


@dataclass
class OperazioneCensimento:
    codice_socio: str
    ordinale: str
    anno_scout: int
    defaults: dict
    trasferimento_da: str | None = None


@dataclass
class OperazioneAllowlist:
    ordinale: str
    email: str


@dataclass
class PianoImportazione:
    anno_scout: int
    gruppi: list[OperazioneGruppo] = field(default_factory=list)
    capi: list[OperazioneCapo] = field(default_factory=list)
    censimenti: list[OperazioneCensimento] = field(default_factory=list)
    allowlist: list[OperazioneAllowlist] = field(default_factory=list)
    capi_da_disattivare: list[str] = field(default_factory=list)
    gruppi_nel_file: set[str] = field(default_factory=set)
    anomalie: list[AnomaliaRiga] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return self.anno_scout > 0


def ultima_importazione_completata(anno_scout: int) -> ImportazioneCSV | None:
    """Sola informazione per l'anteprima (§6.1): nessun blocco, il CSV non ha
    un campo data su cui basare un controllo come quello dei PDF (D-9)."""
    return ImportazioneCSV.objects.filter(anno_scout=anno_scout).order_by("-eseguita_il").first()


def costruisci_piano(risultato: RisultatoParsing) -> PianoImportazione:
    """Sola lettura: nessuna scrittura sul database."""
    if risultato.anno_scout is None:
        return PianoImportazione(anno_scout=0, anomalie=list(risultato.anomalie))

    anno = risultato.anno_scout
    anomalie = list(risultato.anomalie)

    ordinali_nel_file = {r.ordinale for r in risultato.righe}
    codici_presenti = {r.codice_socio for r in risultato.righe} | {
        a.codice_socio for a in risultato.anomalie if a.codice_socio
    }

    gruppi_esistenti = {g.codice: g for g in Gruppo.objects.filter(codice__in=ordinali_nel_file)}

    censimento_piu_recente: dict[str, CensimentoCapo] = {}
    for c in (
        CensimentoCapo.objects.filter(anno_scout__lte=anno)
        .select_related("capo")
        .order_by("capo_id", "-anno_scout")
    ):
        censimento_piu_recente.setdefault(c.capo_id, c)

    gruppi: dict[str, OperazioneGruppo] = {}
    capi: dict[str, OperazioneCapo] = {}
    censimenti: list[OperazioneCensimento] = []

    for r in risultato.righe:
        gruppi[r.ordinale] = OperazioneGruppo(
            ordinale=r.ordinale,
            defaults={
                "nome": r.gruppo_nome,
                "email_istituzionale": r.email_gruppo,
                "indirizzo": r.indirizzo_gruppo,
                "civico": r.civico_gruppo,
                "cap": r.cap_gruppo,
                "comune": r.comune_gruppo,
                "provincia": r.provincia_gruppo,
                "telefono": r.telefono_gruppo,
                "codice_fiscale": r.codice_fiscale_gruppo,
                "parrocchia": r.parrocchia_gruppo,
                "diocesi": r.diocesi_gruppo,
                "denominazione_sociale": r.denominazione_sociale_gruppo,
            },
        )
        capi[r.codice_socio] = OperazioneCapo(
            codice_socio=r.codice_socio,
            defaults={
                "nome": r.nome,
                "cognome": r.cognome,
                "sesso": r.sesso,
                "data_nascita": r.data_nascita,
                "comune_nascita": r.comune_nascita,
                "codice_fiscale": r.codice_fiscale,
                "nazionalita": r.nazionalita,
                "indirizzo": r.indirizzo,
                "civico": r.civico,
                "comune_residenza": r.comune_residenza,
                "provincia_residenza": r.provincia_residenza,
                "cap": r.cap,
                "email": r.email,
                "cellulare": r.cellulare,
                "professione": r.professione,
                "attivo": True,
                "data_disattivazione": None,
            },
        )

        precedente = censimento_piu_recente.get(r.codice_socio)
        trasferimento_da = (
            precedente.gruppo_id
            if precedente is not None and precedente.gruppo_id != r.ordinale
            else None
        )
        censimenti.append(
            OperazioneCensimento(
                codice_socio=r.codice_socio,
                ordinale=r.ordinale,
                anno_scout=anno,
                defaults={
                    "livello_foca": r.livello_foca,
                    "comunita_socio": r.comunita_socio,
                    "status_socio": r.status_socio,
                    "ingresso_coca": r.ingresso_coca,
                    "a_disposizione": True,
                    "branca": "",
                    "is_capogruppo": False,
                },
                trasferimento_da=trasferimento_da,
            )
        )

    allowlist: list[OperazioneAllowlist] = []
    for ordinale, op in gruppi.items():
        esistente = gruppi_esistenti.get(ordinale)
        if esistente is not None and esistente.is_comitato_zona:
            continue
        email = op.defaults["email_istituzionale"].strip()
        if not email:
            anomalie.append(
                AnomaliaRiga(
                    0,
                    AVVISO,
                    "EMAIL GRUPPO",
                    f"Nessuna email istituzionale per {ordinale}: allowlist non aggiornata.",
                    "",
                )
            )
            continue
        allowlist.append(OperazioneAllowlist(ordinale=ordinale, email=email))

    capi_da_disattivare = [
        capo_id
        for capo_id, c in censimento_piu_recente.items()
        if c.gruppo_id in ordinali_nel_file and capo_id not in codici_presenti and c.capo.attivo
    ]

    return PianoImportazione(
        anno_scout=anno,
        gruppi=list(gruppi.values()),
        capi=list(capi.values()),
        censimenti=censimenti,
        allowlist=allowlist,
        capi_da_disattivare=capi_da_disattivare,
        gruppi_nel_file=ordinali_nel_file,
        anomalie=anomalie,
    )


def _anomalia(anomalie: list[AnomaliaRiga], campo: str, dettaglio: str, codice_socio: str) -> None:
    anomalie.append(AnomaliaRiga(0, ERRORE, campo, dettaglio, codice_socio))


def _salva_validato(istanza) -> None:
    istanza.full_clean()
    istanza.save()


def applica_piano(
    piano: PianoImportazione, *, file_originale, utente: Utente | None
) -> ImportazioneCSV:
    """Scrive tutto dentro un'unica transazione. Ogni scrittura è convalidata
    con `full_clean()`: un valore che non supera la validazione finisce
    nel report anomalie invece di essere scritto (anti-confabulazione), e la
    riga collegata viene esclusa senza interrompere le altre."""
    if not piano.valido:
        raise ValueError("Piano non applicabile: anno_scout non determinabile dal file.")

    with transaction.atomic():
        anomalie = list(piano.anomalie)
        conteggi = {
            "capi_nel_file": len(piano.capi),
            "gruppi_creati": 0,
            "gruppi_aggiornati": 0,
            "capi_creati": 0,
            "capi_aggiornati": 0,
            "capi_riattivati": 0,
            "censimenti_creati": 0,
            "censimenti_aggiornati": 0,
            "trasferimenti_rilevati": 0,
            "allowlist_aggiornate": 0,
            "capi_disattivati": 0,
        }

        gruppi_per_codice: dict[str, Gruppo] = {}
        gruppi_falliti: set[str] = set()
        for op_gruppo in piano.gruppi:
            creato, gruppo = _upsert_gruppo(op_gruppo, anomalie)
            if gruppo is None:
                gruppi_falliti.add(op_gruppo.ordinale)
                continue
            gruppi_per_codice[op_gruppo.ordinale] = gruppo
            conteggi["gruppi_creati" if creato else "gruppi_aggiornati"] += 1

        capi_erano_attivi = {
            c.codice_socio: c.attivo
            for c in Capo.objects.filter(
                codice_socio__in=[op_capo.codice_socio for op_capo in piano.capi]
            )
        }

        capi_falliti: set[str] = set()
        capi_riattivati_ids: list[str] = []
        for op_capo in piano.capi:
            capo_prima_attivo = capi_erano_attivi.get(op_capo.codice_socio)
            _, capo = _upsert_capo(op_capo, anomalie)
            if capo is None:
                capi_falliti.add(op_capo.codice_socio)
                continue
            if capo_prima_attivo is None:
                conteggi["capi_creati"] += 1
            else:
                conteggi["capi_aggiornati"] += 1
                if capo_prima_attivo is False:
                    capi_riattivati_ids.append(op_capo.codice_socio)
                    conteggi["capi_riattivati"] += 1

        importazione = ImportazioneCSV(
            file=file_originale, anno_scout=piano.anno_scout, utente=utente
        )
        importazione.save()

        for op_censimento in piano.censimenti:
            if (
                op_censimento.codice_socio in capi_falliti
                or op_censimento.ordinale in gruppi_falliti
            ):
                continue
            gruppo = gruppi_per_codice[op_censimento.ordinale]
            creato, censimento = _upsert_censimento(op_censimento, gruppo, anomalie)
            if censimento is None:
                continue
            conteggi["censimenti_creati" if creato else "censimenti_aggiornati"] += 1

            if (
                op_censimento.trasferimento_da
                and op_censimento.trasferimento_da not in gruppi_falliti
            ):
                TrasferimentoCapo.objects.create(
                    capo_id=op_censimento.codice_socio,
                    anno_scout=op_censimento.anno_scout,
                    gruppo_origine_id=op_censimento.trasferimento_da,
                    gruppo_destino=gruppo,
                    importazione=importazione,
                )
                conteggi["trasferimenti_rilevati"] += 1

        for op_allow in piano.allowlist:
            if op_allow.ordinale in gruppi_falliti:
                continue
            AllowlistGruppo.objects.update_or_create(
                email=op_allow.email,
                defaults={"codice_gruppo": op_allow.ordinale, "origine": OrigineGruppo.IMPORT},
            )
            conteggi["allowlist_aggiornate"] += 1

        capi_disattivati_ids = piano.capi_da_disattivare
        if capi_disattivati_ids:
            Capo.objects.filter(codice_socio__in=capi_disattivati_ids).update(
                attivo=False, data_disattivazione=date.today()
            )
            conteggi["capi_disattivati"] = len(capi_disattivati_ids)

        conteggi["anomalie_bloccanti"] = sum(1 for a in anomalie if a.livello == ERRORE)
        conteggi["avvisi"] = sum(1 for a in anomalie if a.livello == AVVISO)

        importazione.conteggi = conteggi
        importazione.anomalie = [_anomalia_a_dict(a) for a in anomalie]
        importazione.save(update_fields=["conteggi", "anomalie"])
        if capi_disattivati_ids:
            importazione.capi_disattivati.set(
                Capo.objects.filter(codice_socio__in=capi_disattivati_ids)
            )
        if capi_riattivati_ids:
            importazione.capi_riattivati.set(
                Capo.objects.filter(codice_socio__in=capi_riattivati_ids)
            )

    return importazione


def _upsert_gruppo(
    op: OperazioneGruppo, anomalie: list[AnomaliaRiga]
) -> tuple[bool, Gruppo | None]:
    try:
        with transaction.atomic():
            gruppo, creato = Gruppo.objects.get_or_create(
                codice=op.ordinale, defaults={**op.defaults, "origine": OrigineGruppo.IMPORT}
            )
            if not creato:
                for campo, valore in op.defaults.items():
                    setattr(gruppo, campo, valore)
            _salva_validato(gruppo)
            return creato, gruppo
    except ValidationError as exc:
        _anomalia(anomalie, "Gruppo", f"{op.ordinale}: {exc}", "")
        return False, None


def _upsert_capo(op: OperazioneCapo, anomalie: list[AnomaliaRiga]) -> tuple[bool, Capo | None]:
    try:
        with transaction.atomic():
            capo, creato = Capo.objects.get_or_create(
                codice_socio=op.codice_socio, defaults=op.defaults
            )
            if not creato:
                for campo, valore in op.defaults.items():
                    setattr(capo, campo, valore)
            _salva_validato(capo)
            return creato, capo
    except ValidationError as exc:
        _anomalia(anomalie, "Capo", str(exc), op.codice_socio)
        return False, None


def _upsert_censimento(
    op: OperazioneCensimento, gruppo: Gruppo, anomalie: list[AnomaliaRiga]
) -> tuple[bool, CensimentoCapo | None]:
    try:
        with transaction.atomic():
            censimento, creato = CensimentoCapo.objects.get_or_create(
                capo_id=op.codice_socio,
                anno_scout=op.anno_scout,
                defaults={**op.defaults, "gruppo": gruppo},
            )
            if not creato:
                for campo, valore in op.defaults.items():
                    setattr(censimento, campo, valore)
                censimento.gruppo = gruppo
            _salva_validato(censimento)
            return creato, censimento
    except ValidationError as exc:
        _anomalia(anomalie, "CensimentoCapo", str(exc), op.codice_socio)
        return False, None


def _anomalia_a_dict(a: AnomaliaRiga) -> dict:
    return {
        "numero_riga": a.numero_riga,
        "livello": a.livello,
        "campo": a.campo,
        "dettaglio": a.dettaglio,
        "codice_socio": a.codice_socio,
    }
