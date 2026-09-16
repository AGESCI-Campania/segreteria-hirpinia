"""Geocoding delle località estere al primo uso (D-56): la tabella locale
dei comuni italiani (F1) è la fonte primaria e non passa mai da qui — questo
modulo è **solo** il fallback per l'estero, stesso provider del routing
(OpenRouteService), stesso principio anti-confabulazione: mai una coordinata
indovinata se il geocoding non trova nulla o la risposta è inservibile.

**Limite dichiarato**: la ricerca di una località già salvata è per nome
esatto (case-insensitive), senza disambiguare per stato — due città omonime
in paesi diversi (es. "Paris" Francia/Texas) collidono sulla stessa riga.
Non specificato da D-56, che parla solo di "salvata come record locale al
primo uso"; da rivedere se emerge un caso reale."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from .models import Localita
from .routing import BackendRoutingNonDisponibile

SEI_DECIMALI = Decimal("0.000001")


def _interroga_provider(nome: str, stato: str) -> dict:
    """Isolato in una funzione propria così i test possono sostituirla
    senza toccare la rete, stesso pattern di `distanza_km_tra_localita`."""
    import openrouteservice
    from openrouteservice.exceptions import ApiError, HTTPError, Timeout

    api_key = settings.NOTA_SPESE_OPENROUTESERVICE_API_KEY
    if not api_key:
        raise BackendRoutingNonDisponibile("NOTA_SPESE_OPENROUTESERVICE_API_KEY non configurata.")

    client = openrouteservice.Client(key=api_key)
    try:
        return client.pelias_search(
            text=nome,
            country=stato or None,
            layers=["locality"],
            size=1,
        )
    except (ApiError, HTTPError, Timeout) as errore:
        raise BackendRoutingNonDisponibile(
            f"OpenRouteService (geocoding) non ha risposto: {errore}"
        ) from errore


def geocodifica_localita_estera(nome: str, stato: str = "") -> Localita:
    """D-56: ricerca esterna come fallback solo per l'estero — restituisce
    il record locale già esistente se il nome è già stato geocodificato
    (dalla seconda volta niente chiamata al provider), altrimenti
    interroga OpenRouteService e salva il risultato. Solo città (`layers=
    ["locality"]`), non indirizzo completo, come richiesto."""
    esistente = Localita.objects.filter(nome__iexact=nome, estero=True).first()
    if esistente is not None:
        return esistente

    risposta = _interroga_provider(nome, stato)
    features = risposta.get("features") or []
    if not features:
        raise BackendRoutingNonDisponibile(
            f"Nessun risultato di geocoding per {nome!r}: la località va inserita a mano."
        )

    proprieta = features[0].get("properties", {})
    try:
        lon, lat = features[0]["geometry"]["coordinates"]
    except (KeyError, ValueError) as errore:
        raise BackendRoutingNonDisponibile(
            f"Risposta di geocoding senza coordinate utilizzabili per {nome!r}."
        ) from errore

    return Localita.objects.create(
        nome=nome,
        estero=True,
        stato=proprieta.get("country") or stato,
        latitudine=Decimal(str(lat)).quantize(SEI_DECIMALI),
        longitudine=Decimal(str(lon)).quantize(SEI_DECIMALI),
    )
