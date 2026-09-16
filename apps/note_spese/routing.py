"""Backend di routing astratto per il calcolo delle distanze (D-55): il
client concreto è selezionabile da `settings.NOTA_SPESE_ROUTING_BACKEND`,
mai importato direttamente da chi ha bisogno solo della distanza. I
risultati vanno in cache sulla coppia origine-destinazione (D-55) — qui
tramite il framework cache di Django, già configurato per il progetto
(`DatabaseCache` in produzione, `LocMemCache` in sviluppo/test)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from .models import Localita


class BackendRoutingNonDisponibile(Exception):
    """Il backend configurato non ha potuto calcolare la distanza (chiave
    API mancante, errore di rete, risposta inattesa dal provider) — mai un
    valore indovinato al suo posto (anti-confabulazione)."""


class BackendRouting(ABC):
    """`nome` è persistito su `RigaSpesa.distanza_backend` (D-54): deve
    restare stabile, non tradotto né rinominato in futuro senza una
    migrazione dei dati già congelati."""

    nome: str

    @abstractmethod
    def distanza_km(
        self, lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal
    ) -> Decimal: ...


class BackendOpenRouteService(BackendRouting):
    """D-55: proposta dei requisiti, confermata da Andrea. Profilo
    `driving-car` (unica modalità pertinente per un rimborso chilometrico
    auto — non è un'opzione perché il modulo non calcola percorrenze non
    stradali)."""

    nome = "openrouteservice"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (
            api_key if api_key is not None else settings.NOTA_SPESE_OPENROUTESERVICE_API_KEY
        )
        if not self.api_key:
            raise BackendRoutingNonDisponibile(
                "NOTA_SPESE_OPENROUTESERVICE_API_KEY non configurata."
            )

    def distanza_km(self, lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> Decimal:
        import openrouteservice
        from openrouteservice.exceptions import ApiError, HTTPError, Timeout

        client = openrouteservice.Client(key=self.api_key)
        try:
            risposta = client.directions(
                coordinates=[(float(lon1), float(lat1)), (float(lon2), float(lat2))],
                profile="driving-car",
                format="json",
            )
        except (ApiError, HTTPError, Timeout) as errore:
            raise BackendRoutingNonDisponibile(
                f"OpenRouteService non ha risposto: {errore}"
            ) from errore
        try:
            metri = risposta["routes"][0]["summary"]["distance"]
        except (KeyError, IndexError) as errore:
            raise BackendRoutingNonDisponibile(
                "Risposta di OpenRouteService senza una distanza utilizzabile."
            ) from errore
        return (Decimal(str(metri)) / Decimal(1000)).quantize(Decimal("0.1"))


_BACKEND_PER_NOME: dict[str, type[BackendRouting]] = {
    BackendOpenRouteService.nome: BackendOpenRouteService,
}


def backend_corrente() -> BackendRouting:
    nome = settings.NOTA_SPESE_ROUTING_BACKEND
    classe = _BACKEND_PER_NOME.get(nome)
    if classe is None:
        raise BackendRoutingNonDisponibile(f"Backend di routing non riconosciuto: {nome!r}.")
    return classe()


def distanza_km_tra_localita(partenza: Localita, arrivo: Localita) -> tuple[Decimal, str]:
    """D-55: cache sulla coppia origine-destinazione, a tempo indefinito —
    inferenza dichiarata (non specificata dai requisiti): la distanza
    stradale fra due comuni non cambia nella pratica, a differenza di un
    dato che si aggiorna nel tempo. Ritorna `(distanza_km, nome_backend)`,
    non ancora persistito sulla riga (D-54 è il prossimo passo)."""
    chiave = f"note_spese:distanza_km:{partenza.pk}:{arrivo.pk}"
    risultato = cache.get(chiave)
    if risultato is not None:
        return risultato
    backend = backend_corrente()
    distanza = backend.distanza_km(
        partenza.latitudine, partenza.longitudine, arrivo.latitudine, arrivo.longitudine
    )
    risultato = (distanza, backend.nome)
    cache.set(chiave, risultato, timeout=None)
    return risultato
