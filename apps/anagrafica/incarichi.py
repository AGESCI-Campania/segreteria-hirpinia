"""Assegnazione manuale degli incarichi in unità (M3b, D-32, D-34): il ponte
fra un trasferimento rilevato dal CSV e un'autorizzazione del gruppo di
destinazione non ancora arrivata. Unico punto autorizzato a scrivere
IncaricoUnita al di fuori dell'import PDF."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import gruppi_visibili
from apps.accounts.ruoli_derivati import sincronizza_ruoli_cg
from apps.organizzazione.models import Gruppo

from .derivazioni import ricalcola_derivati_capo, ricalcola_pattuglia
from .models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)

# D-08/M7: la branca è obbligatoria in UI solo per queste due funzioni (capo
# unità/aiuto capo unità hanno sempre un'unità e quindi una branca reale);
# per le altre non ha lo stesso significato (es. CAPO_GRUPPO opera a livello
# di Comunità Capi) e resta facoltativa — mai fidarsi solo del client,
# controllato di nuovo qui.
FUNZIONI_CON_BRANCA_OBBLIGATORIA = frozenset(
    {FunzioneIncarico.CAPO_UNITA, FunzioneIncarico.AIUTO_CAPO_UNITA}
)

# Più ampio di RUOLI_IMPORT_ANAGRAFICA (apps.anagrafica.importazione): include
# CG, che non importa PDF ma assegna incarichi sul proprio perimetro (A-7).
RUOLI_ASSEGNAZIONE_INCARICHI = frozenset(
    {Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ, Ruolo.Tipo.CG}
)

# Deciso con l'utente: D-32 vale alla lettera, la ricerca cross-gruppo di
# D-34 è riservata a chi ha perimetro di Zona (stesso insieme dell'import PDF,
# CG escluso).
RUOLI_RICERCA_CAPO = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ})


@dataclass(frozen=True)
class CapoTrovato:
    """Solo i dati necessari a confermare l'identità (D-34): mai recapiti."""

    codice_socio: str
    nome: str
    cognome: str
    gruppo_censimento_codice: str
    gruppo_censimento_nome: str


def cerca_capo_per_codice_socio(codice_socio: str, *, anno_scout: int) -> CapoTrovato | None:
    """Solo per codice socio esatto: mai icontains, mai elenco sfogliabile."""
    censimento = (
        CensimentoCapo.objects.filter(capo_id=codice_socio, anno_scout=anno_scout)
        .select_related("capo", "gruppo")
        .first()
    )
    if censimento is None:
        return None
    return CapoTrovato(
        codice_socio=censimento.capo_id,
        nome=censimento.capo.nome,
        cognome=censimento.capo.cognome,
        gruppo_censimento_codice=censimento.gruppo_id,
        gruppo_censimento_nome=censimento.gruppo.nome,
    )


def _verifica_perimetro(
    utente: Utente,
    *,
    anno_scout: int,
    gruppo_servizio: Gruppo,
    gruppo_censimento: Gruppo | None = None,
) -> None:
    """Perimetro di D-32 applicato alla lettera (decisione presa con
    l'utente): un CG opera solo su capi censiti in un gruppo del proprio
    perimetro, e assegna incarichi di servizio solo nel proprio perimetro.
    Per SEGRETERIA/ADMIN/RDZ `gruppi_visibili` copre già tutta la Zona."""
    visibili = {g.codice for g in gruppi_visibili(utente, anno_scout)}
    if gruppo_servizio.codice not in visibili:
        raise PermissionDenied(
            f"{utente}: {gruppo_servizio.codice} non è nel proprio perimetro operativo."
        )
    if gruppo_censimento is not None and gruppo_censimento.codice not in visibili:
        raise PermissionDenied(
            f"{utente}: il capo censito in {gruppo_censimento.codice} non è nel proprio perimetro operativo."
        )


def _notifica(destinatario_email: str, oggetto: str, template: str, contesto: dict) -> None:
    send_mail(
        subject=oggetto,
        message=render_to_string(template, contesto),
        from_email=None,
        recipient_list=[destinatario_email],
        fail_silently=True,
    )


def _notifica_incarico(
    incarico: IncaricoUnita, censimento: CensimentoCapo, *, template: str, oggetto: str
) -> None:
    destinatari = set()
    if censimento.gruppo.email_istituzionale:
        destinatari.add(censimento.gruppo.email_istituzionale)
    destinatari |= set(
        Utente.objects.filter(ruoli__tipo=Ruolo.Tipo.SEGRETERIA, ruoli__attivo=True)
        .values_list("email", flat=True)
        .distinct()
    )
    for email in destinatari:
        _notifica(email, oggetto, template, {"incarico": incarico, "censimento": censimento})


@transaction.atomic
def assegna_incarico_manuale(
    *,
    utente: Utente,
    codice_socio: str,
    anno_scout: int,
    gruppo_servizio: Gruppo,
    codice_unita: str,
    nome_unita: str,
    branca: str,
    genere_unita: str,
    funzione: str,
    livello_foca: int | None,
) -> IncaricoUnita:
    censimento = (
        CensimentoCapo.objects.filter(capo_id=codice_socio, anno_scout=anno_scout)
        .select_related("capo__utente", "gruppo")
        .first()
    )
    if censimento is None:
        raise ValidationError(f"Il capo {codice_socio} non è censito nell'anno {anno_scout}.")

    _verifica_perimetro(
        utente,
        anno_scout=anno_scout,
        gruppo_servizio=gruppo_servizio,
        gruppo_censimento=censimento.gruppo,
    )

    if funzione in FUNZIONI_CON_BRANCA_OBBLIGATORIA and not branca:
        raise ValidationError({"branca": "Obbligatoria per Capo unità/Aiuto capo unità."})
    branca = branca or BrancaUnita.SCONOSCIUTA

    incarico = IncaricoUnita(
        capo_id=codice_socio,
        anno_scout=anno_scout,
        gruppo_servizio=gruppo_servizio,
        codice_unita=codice_unita,
        nome_unita=nome_unita,
        branca=branca,
        genere_unita=genere_unita,
        funzione=funzione,
        livello_foca=livello_foca,
        origine=OrigineIncarico.MANUALE,
        assegnato_da=utente,
    )
    incarico.full_clean()
    incarico.save()

    branca_prima = censimento.branca
    censimento_dopo = ricalcola_derivati_capo(codice_socio, anno_scout)
    for b in {branca_prima, censimento_dopo.branca if censimento_dopo else branca_prima}:
        ricalcola_pattuglia(b, anno_scout)

    if funzione == FunzioneIncarico.CAPO_GRUPPO and censimento.capo.utente_id:
        gruppi_capogruppo = frozenset(
            IncaricoUnita.objects.filter(
                capo_id=codice_socio,
                anno_scout=anno_scout,
                funzione=FunzioneIncarico.CAPO_GRUPPO,
                cessato_il__isnull=True,
            ).values_list("gruppo_servizio_id", flat=True)
        )
        sincronizza_ruoli_cg(
            utente=censimento.capo.utente, gruppi_capogruppo=gruppi_capogruppo, assegnato_da=utente
        )

    _notifica_incarico(
        incarico,
        censimento,
        template="anagrafica/email/incarico_assegnato.txt",
        oggetto="Catello — nuovo incarico assegnato",
    )

    return incarico


@transaction.atomic
def cessa_incarico_manuale(*, utente: Utente, incarico: IncaricoUnita) -> None:
    if incarico.origine != OrigineIncarico.MANUALE:
        raise ValidationError(
            "Solo un incarico manuale può essere cessato da qui: un incarico IMPORT si "
            "sostituisce solo importando una nuova autorizzazione (D-32)."
        )
    if incarico.cessato_il is not None:
        raise ValidationError("Incarico già cessato.")

    censimento = (
        CensimentoCapo.objects.filter(capo_id=incarico.capo_id, anno_scout=incarico.anno_scout)
        .select_related("capo__utente", "gruppo")
        .first()
    )
    _verifica_perimetro(
        utente,
        anno_scout=incarico.anno_scout,
        gruppo_servizio=incarico.gruppo_servizio,
        gruppo_censimento=censimento.gruppo if censimento else None,
    )

    branca_prima = censimento.branca if censimento else ""
    incarico.cessato_il = timezone.now()
    incarico.save(update_fields=["cessato_il"])

    censimento_dopo = ricalcola_derivati_capo(incarico.capo_id, incarico.anno_scout)
    for b in {branca_prima, censimento_dopo.branca if censimento_dopo else branca_prima}:
        ricalcola_pattuglia(b, incarico.anno_scout)

    if incarico.funzione == FunzioneIncarico.CAPO_GRUPPO:
        capo = Capo.objects.filter(pk=incarico.capo_id).select_related("utente").first()
        if capo is not None and capo.utente_id:
            gruppi_capogruppo = frozenset(
                IncaricoUnita.objects.filter(
                    capo_id=incarico.capo_id,
                    anno_scout=incarico.anno_scout,
                    funzione=FunzioneIncarico.CAPO_GRUPPO,
                    cessato_il__isnull=True,
                ).values_list("gruppo_servizio_id", flat=True)
            )
            sincronizza_ruoli_cg(
                utente=capo.utente, gruppi_capogruppo=gruppi_capogruppo, assegnato_da=utente
            )

    if censimento is not None:
        _notifica_incarico(
            incarico,
            censimento,
            template="anagrafica/email/incarico_cessato.txt",
            oggetto="Catello — incarico cessato",
        )
