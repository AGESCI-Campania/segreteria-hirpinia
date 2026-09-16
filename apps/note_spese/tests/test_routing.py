"""D-55: backend di routing astratto, cache sulla coppia origine-destinazione.
Nessuna chiamata di rete reale: il backend concreto è sostituito con un doppio
di test."""

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.note_spese import routing
from apps.note_spese.models import Localita
from apps.note_spese.routing import (
    BackendOpenRouteService,
    BackendRouting,
    BackendRoutingNonDisponibile,
    backend_corrente,
    distanza_km_tra_localita,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _pulisci_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def partenza() -> Localita:
    return Localita.objects.create(
        nome="Avellino", latitudine=Decimal("40.913637"), longitudine=Decimal("14.790168")
    )


@pytest.fixture
def arrivo() -> Localita:
    return Localita.objects.create(
        nome="Napoli", latitudine=Decimal("40.851775"), longitudine=Decimal("14.268121")
    )


class BackendFinto(BackendRouting):
    nome = "finto"

    def __init__(self) -> None:
        self.chiamate = 0

    def distanza_km(self, lat1, lon1, lat2, lon2) -> Decimal:
        self.chiamate += 1
        return Decimal("42.0")


class TestBackendOpenRouteService:
    @override_settings(NOTA_SPESE_OPENROUTESERVICE_API_KEY="")
    def test_senza_chiave_api_solleva_errore(self) -> None:
        with pytest.raises(BackendRoutingNonDisponibile):
            BackendOpenRouteService()

    def test_con_chiave_api_esplicita_non_serve_la_impostazione(self) -> None:
        backend = BackendOpenRouteService(api_key="una-chiave")
        assert backend.api_key == "una-chiave"


class TestBackendCorrente:
    @override_settings(NOTA_SPESE_ROUTING_BACKEND="non-esiste")
    def test_backend_non_riconosciuto_solleva_errore(self) -> None:
        with pytest.raises(BackendRoutingNonDisponibile):
            backend_corrente()

    @override_settings(
        NOTA_SPESE_ROUTING_BACKEND="openrouteservice",
        NOTA_SPESE_OPENROUTESERVICE_API_KEY="una-chiave",
    )
    def test_backend_riconosciuto_restituisce_openrouteservice(self) -> None:
        assert isinstance(backend_corrente(), BackendOpenRouteService)


class TestDistanzaKmTraLocalita:
    def test_usa_il_backend_e_mette_in_cache(self, monkeypatch, partenza, arrivo) -> None:
        finto = BackendFinto()
        monkeypatch.setattr(routing, "backend_corrente", lambda: finto)

        distanza, nome_backend = distanza_km_tra_localita(partenza, arrivo)

        assert distanza == Decimal("42.0")
        assert nome_backend == "finto"
        assert finto.chiamate == 1

    def test_seconda_chiamata_non_richiama_il_backend(self, monkeypatch, partenza, arrivo) -> None:
        finto = BackendFinto()
        monkeypatch.setattr(routing, "backend_corrente", lambda: finto)

        distanza_km_tra_localita(partenza, arrivo)
        distanza_km_tra_localita(partenza, arrivo)

        assert finto.chiamate == 1

    def test_coppie_diverse_non_condividono_la_cache(self, monkeypatch, partenza, arrivo) -> None:
        finto = BackendFinto()
        monkeypatch.setattr(routing, "backend_corrente", lambda: finto)
        terza = Localita.objects.create(
            nome="Salerno", latitudine=Decimal("40.674004"), longitudine=Decimal("14.759138")
        )

        distanza_km_tra_localita(partenza, arrivo)
        distanza_km_tra_localita(partenza, terza)

        assert finto.chiamate == 2
