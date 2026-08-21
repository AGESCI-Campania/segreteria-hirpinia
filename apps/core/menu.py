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
from apps.accounts.views import RUOLI_CHE_INVITANO
from apps.anagrafica.esportazione import RUOLI_EXPORT_ANAGRAFICA, RUOLI_VISUALIZZAZIONE_ESPORTAZIONI
from apps.anagrafica.importazione import RUOLI_IMPORT_ANAGRAFICA
from apps.anagrafica.incarichi import RUOLI_ASSEGNAZIONE_INCARICHI, RUOLI_RICERCA_CAPO
from apps.contributi.inserimento import RUOLI_GESTIONE_PARTECIPAZIONI
from apps.core.views import RUOLI_GESTIONE_IMPOSTAZIONI
from apps.organizzazione.gruppi import RUOLI_GESTIONE_GRUPPI

RUOLI_GESTIONE_DELEGHE_ZONA = frozenset({Ruolo.Tipo.ADMIN, Ruolo.Tipo.SEGRETERIA})


@dataclass(frozen=True)
class VoceMenu:
    etichetta: str
    url: str


def _voce(etichetta: str, url_name: str) -> VoceMenu:
    return VoceMenu(etichetta, reverse(url_name))


@dataclass(frozen=True)
class SezioneMenu:
    etichetta: str
    voci: list[VoceMenu]


def sezioni_menu(utente: Utente | AnonymousUser) -> list[SezioneMenu]:
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
        voci_anagrafica.append(_voce("Importa anagrafica soci", "anagrafica:importazione_lista"))
        voci_anagrafica.append(
            _voce("Importa autorizzazioni", "anagrafica:importazione_autorizzazioni_lista")
        )
    if consentito(RUOLI_RICERCA_CAPO):
        voci_anagrafica.append(_voce("Cerca capo censito altrove", "anagrafica:ricerca_capo"))
    if consentito(RUOLI_ASSEGNAZIONE_INCARICHI):
        voci_anagrafica.append(_voce("Assegna incarico", "anagrafica:assegna_incarico"))
    if consentito(RUOLI_EXPORT_ANAGRAFICA):
        voci_anagrafica.append(_voce("Esporta anagrafica", "anagrafica:esportazione"))
    if consentito(RUOLI_VISUALIZZAZIONE_ESPORTAZIONI):
        voci_anagrafica.append(_voce("Registro esportazioni", "anagrafica:esportazione_lista"))
    if voci_anagrafica:
        sezioni.append(SezioneMenu("Anagrafica", voci_anagrafica))

    voci_contributi = []
    if consentito(RUOLI_GESTIONE_PARTECIPAZIONI):
        voci_contributi.append(_voce("Campagne Fo.Ca.", "contributi:campagna_lista"))
    if voci_contributi:
        sezioni.append(SezioneMenu("Contributi", voci_contributi))

    voci_organizzazione = []
    if consentito(RUOLI_GESTIONE_GRUPPI):
        voci_organizzazione.append(_voce("Gruppi", "organizzazione:gruppo_lista"))
    if voci_organizzazione:
        sezioni.append(SezioneMenu("Organizzazione", voci_organizzazione))

    voci_account = [_voce("Le mie deleghe", "accounts:deleghe_lista")]
    if consentito(RUOLI_CHE_INVITANO, solo_diretti=True):
        voci_account.append(_voce("Inviti", "accounts:invito_lista"))
    if consentito(RUOLI_GESTIONE_DELEGHE_ZONA, solo_diretti=True):
        voci_account.append(_voce("Deleghe di Zona", "accounts:deleghe_zona"))
    sezioni.append(SezioneMenu("Account", voci_account))

    if consentito(RUOLI_GESTIONE_IMPOSTAZIONI, solo_diretti=True):
        sezioni.append(SezioneMenu("Amministrazione", [_voce("Impostazioni", "core:impostazioni")]))

    return sezioni
