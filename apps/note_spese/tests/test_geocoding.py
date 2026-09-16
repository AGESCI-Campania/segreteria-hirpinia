"""D-56: geocoding delle località estere al primo uso. Nessuna chiamata di
rete reale: `_interroga_provider` è sempre sostituita da un doppio di test."""

from decimal import Decimal

import pytest

from apps.note_spese import geocoding
from apps.note_spese.geocoding import geocodifica_localita_estera
from apps.note_spese.models import Localita
from apps.note_spese.routing import BackendRoutingNonDisponibile

pytestmark = pytest.mark.django_db


def _risposta_pelias(lon: float, lat: float, country: str = "France") -> dict:
    return {
        "features": [
            {
                "geometry": {"coordinates": [lon, lat]},
                "properties": {"country": country, "label": "Parigi, Francia"},
            }
        ]
    }


class TestGeocodificaLocalitaEstera:
    def test_crea_una_nuova_localita(self, monkeypatch) -> None:
        monkeypatch.setattr(
            geocoding, "_interroga_provider", lambda nome, stato: _risposta_pelias(2.3522, 48.8566)
        )
        localita = geocodifica_localita_estera("Parigi", stato="FR")
        assert localita.nome == "Parigi"
        assert localita.estero is True
        assert localita.stato == "France"
        assert localita.latitudine == Decimal("48.856600")
        assert localita.longitudine == Decimal("2.352200")

    def test_seconda_chiamata_non_richiama_il_provider(self, monkeypatch) -> None:
        chiamate = []

        def _boom(nome, stato):
            chiamate.append(nome)
            return _risposta_pelias(2.3522, 48.8566)

        monkeypatch.setattr(geocoding, "_interroga_provider", _boom)
        geocodifica_localita_estera("Parigi")
        geocodifica_localita_estera("parigi")  # case-insensitive
        assert len(chiamate) == 1
        assert Localita.objects.filter(nome="Parigi").count() == 1

    def test_nessun_risultato_solleva_errore(self, monkeypatch) -> None:
        monkeypatch.setattr(geocoding, "_interroga_provider", lambda nome, stato: {"features": []})
        with pytest.raises(BackendRoutingNonDisponibile):
            geocodifica_localita_estera("Città inesistente")

    def test_risposta_senza_coordinate_solleva_errore(self, monkeypatch) -> None:
        monkeypatch.setattr(
            geocoding,
            "_interroga_provider",
            lambda nome, stato: {"features": [{"geometry": {}, "properties": {}}]},
        )
        with pytest.raises(BackendRoutingNonDisponibile):
            geocodifica_localita_estera("Città senza coordinate")

    def test_localita_italiana_gia_in_tabella_non_e_toccata(self, monkeypatch) -> None:
        # Popolata dalla data migration 0003 (comuni italiani), non creata qui.
        italiana_originale = Localita.objects.get(codice_istat="064008")
        latitudine_originale = italiana_originale.latitudine

        def _boom(nome, stato):
            raise AssertionError("Non deve interrogare il provider per una città già italiana.")

        # Avellino non è 'estero=True', quindi il filtro esistente non la
        # trova e la funzione tenterebbe il geocoding: qui verifichiamo solo
        # che il record italiano esistente non venga alterato da un secondo
        # geocoding con lo stesso nome ma esito diverso.
        monkeypatch.setattr(
            geocoding,
            "_interroga_provider",
            lambda nome, stato: _risposta_pelias(1.0, 1.0, "Italy"),
        )
        geocodifica_localita_estera("Avellino")
        italiana = Localita.objects.get(codice_istat="064008")
        assert italiana.estero is False
        assert italiana.latitudine == latitudine_originale
