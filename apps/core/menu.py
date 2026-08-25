"""Voci di navigazione principali, filtrate per ruolo effettivo dell'utente.

Riusa le stesse costanti `RUOLI_*` già usate dalle view per il controllo
d'accesso (`apps.accounts.mixins.RuoloRequiredMixin`): una voce compare nel
menu se e solo se l'utente potrebbe davvero accedere alla view corrispondente,
non va duplicata la regola di perimetro qui.
"""

from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.accounts.models import Ruolo, Utente
from apps.accounts.permessi import ruoli_effettivi
from apps.accounts.ruoli import RUOLI_GESTIONE_RUOLI
from apps.accounts.views import RUOLI_CHE_INVITANO
from apps.anagrafica.esportazione import RUOLI_EXPORT_ANAGRAFICA, RUOLI_VISUALIZZAZIONE_ESPORTAZIONI
from apps.anagrafica.importazione import RUOLI_IMPORT_ANAGRAFICA
from apps.anagrafica.incarichi import RUOLI_RICERCA_CAPO
from apps.contributi.inserimento import RUOLI_GESTIONE_PARTECIPAZIONI
from apps.core.views import RUOLI_GESTIONE_IMPOSTAZIONI
from apps.organizzazione.gruppi import RUOLI_GESTIONE_GRUPPI

RUOLI_GESTIONE_DELEGHE_ZONA = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA})


@dataclass(frozen=True)
class VoceMenu:
    etichetta: str
    url: str
    icona: str


def _voce(etichetta: str, url_name: str, icona: str, args: list | None = None) -> VoceMenu:
    return VoceMenu(etichetta, reverse(url_name, args=args), icona)


@dataclass(frozen=True)
class SezioneMenu:
    etichetta: str
    icona: str
    voci: list[VoceMenu]


def sezioni_menu(utente: Utente | AnonymousUser) -> list[SezioneMenu]:
    """Le 4 sezioni principali della sidebar (Anagrafica include la gestione
    gruppi: sono entrambe informazioni sul censimento, non moduli separati agli
    occhi dell'utente)."""
    if not utente.is_authenticated:
        return []
    assert isinstance(utente, Utente)

    ruoli = ruoli_effettivi(utente)
    tipi_ruolo = {r.tipo for r in ruoli}
    tipi_ruolo_diretti = {r.tipo for r in ruoli if not r.is_delega}

    def consentito(ruoli_ammessi: frozenset[str], *, solo_diretti: bool = False) -> bool:
        tipi = tipi_ruolo_diretti if solo_diretti else tipi_ruolo
        return bool(tipi & ruoli_ammessi)

    sezioni: list[SezioneMenu] = []

    voci_anagrafica = []
    if consentito(RUOLI_IMPORT_ANAGRAFICA):
        voci_anagrafica.append(
            _voce("Importa", "anagrafica:importazione_cruscotto", "cloud-upload")
        )
    if (
        consentito(RUOLI_EXPORT_ANAGRAFICA)
        or consentito(RUOLI_RICERCA_CAPO)
        or consentito(RUOLI_VISUALIZZAZIONE_ESPORTAZIONI)
    ):
        voci_anagrafica.append(
            _voce("Visualizza anagrafica", "anagrafica:esportazione", "cloud-download")
        )
    if consentito(RUOLI_GESTIONE_GRUPPI):
        voci_anagrafica.append(_voce("Gruppi", "organizzazione:gruppo_lista", "diagram-3"))
    else:
        # "Il mio gruppo" (D-35): un CG senza RUOLI_GESTIONE_GRUPPI non vede
        # "Gruppi" e non avrebbe altrimenti un punto di accesso a
        # gruppo_gestione. Grazie a D-35 un CG ha al più un gruppo reale +
        # l'eventuale E9001 derivato (che però implica RDZ, già coperto dal
        # ramo sopra): in pratica qui c'è sempre al più un gruppo, ma il ramo
        # multiplo resta gestito esplicitamente, non assunto.
        gruppi_cg = {
            r.gruppo.codice: r.gruppo for r in ruoli if r.tipo == Ruolo.Tipo.CG and r.gruppo
        }
        if len(gruppi_cg) == 1:
            (codice,) = gruppi_cg
            voci_anagrafica.append(
                _voce("Il mio gruppo", "organizzazione:gruppo_gestione", "diagram-3", args=[codice])
            )
        else:
            for codice, gr in sorted(gruppi_cg.items()):
                voci_anagrafica.append(
                    _voce(
                        f"Il mio gruppo — {gr.nome}",
                        "organizzazione:gruppo_gestione",
                        "diagram-3",
                        args=[codice],
                    )
                )
    if voci_anagrafica:
        sezioni.append(SezioneMenu("Anagrafica", "people-fill", voci_anagrafica))

    voci_contributi = []
    if consentito(RUOLI_GESTIONE_PARTECIPAZIONI):
        voci_contributi.append(
            _voce("Contributo Fo.Ca.", "contributi:campagna_lista", "calendar2-check")
        )
    if voci_contributi:
        sezioni.append(SezioneMenu("Moduli", "cash-coin", voci_contributi))

    voci_account = [_voce("Le mie deleghe", "accounts:deleghe_lista", "person-lines-fill")]
    if consentito(RUOLI_CHE_INVITANO, solo_diretti=True):
        voci_account.append(_voce("Inviti", "accounts:invito_lista", "envelope"))
    if consentito(RUOLI_GESTIONE_DELEGHE_ZONA, solo_diretti=True):
        voci_account.append(_voce("Deleghe di Zona", "accounts:deleghe_zona", "people"))
    sezioni.append(SezioneMenu("Account", "person-circle", voci_account))

    voci_amministrazione = []
    if consentito(RUOLI_GESTIONE_GRUPPI):
        voci_amministrazione.append(
            _voce("Allowlist gruppi", "organizzazione:allowlist_lista", "shield-check")
        )
    if consentito(RUOLI_GESTIONE_RUOLI, solo_diretti=True):
        voci_amministrazione.append(_voce("Ruoli", "accounts:ruolo_lista", "person-badge"))
    if consentito(RUOLI_GESTIONE_IMPOSTAZIONI, solo_diretti=True):
        voci_amministrazione.append(_voce("Impostazioni", "core:impostazioni", "sliders"))
    if voci_amministrazione:
        sezioni.append(SezioneMenu("Amministrazione", "gear-fill", voci_amministrazione))

    return sezioni
