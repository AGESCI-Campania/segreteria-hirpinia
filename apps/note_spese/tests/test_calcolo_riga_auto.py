"""D-52/D-53/D-54: calcolo dell'importo delle righe auto. Nessuna chiamata
di rete reale: `distanza_km_tra_localita` è sempre sostituita da un doppio
di test che restituisce valori fissi."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.note_spese import calcolo_riga_auto
from apps.note_spese.calcolo_riga_auto import (
    calcola_importo_altri_spostamenti,
    calcola_importo_andata_ritorno,
    calcola_importo_riga_auto,
)
from apps.note_spese.models import (
    CategoriaSpesa,
    Evento,
    Localita,
    NotaSpese,
    RigaSpesa,
    RigaSpesaPasseggero,
    TariffaChilometrica,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tariffe():
    TariffaChilometrica.objects.create(
        fascia="TRE_O_PIU", importo_km=Decimal("0.30"), valida_dal=datetime.date(2020, 1, 1)
    )
    TariffaChilometrica.objects.create(
        fascia="BREVE", importo_km=Decimal("0.20"), valida_dal=datetime.date(2020, 1, 1)
    )
    TariffaChilometrica.objects.create(
        fascia="LUNGA", importo_km=Decimal("0.15"), valida_dal=datetime.date(2020, 1, 1)
    )


@pytest.fixture(autouse=True)
def _niente_rete(monkeypatch):
    """Fallisce rumorosamente se un test finisce per chiamare il backend di
    routing reale senza averlo sostituito esplicitamente."""

    def _boom(partenza, arrivo):
        raise AssertionError("Test che chiama la rete reale: mancava un monkeypatch.")

    monkeypatch.setattr(calcolo_riga_auto, "distanza_km_tra_localita", _boom)


@pytest.fixture
def categoria_altro() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(
        nome="Auto altri spostamenti test",
        tipo_calcolo="CHILOMETRICO",
        sottotipo_chilometrico="ALTRO",
    )


@pytest.fixture
def categoria_andata_ritorno() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(
        nome="Auto andata ritorno test",
        tipo_calcolo="CHILOMETRICO",
        sottotipo_chilometrico="ANDATA_RITORNO",
    )


@pytest.fixture
def avellino() -> Localita:
    return Localita.objects.create(
        nome="Avellino", latitudine=Decimal("40.913637"), longitudine=Decimal("14.790168")
    )


@pytest.fixture
def napoli() -> Localita:
    return Localita.objects.create(
        nome="Napoli", latitudine=Decimal("40.851775"), longitudine=Decimal("14.268121")
    )


@pytest.fixture
def nota(gruppo, capo_persona, evento) -> NotaSpese:
    return NotaSpese.objects.create(
        beneficiario=capo_persona, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo_persona():
    from apps.anagrafica.models import Capo

    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


def _riga_auto(nota, categoria, avellino, napoli, data=datetime.date(2027, 7, 2)):
    return RigaSpesa.objects.create(
        nota=nota,
        categoria=categoria,
        data=data,
        localita_partenza=avellino,
        localita_arrivo=napoli,
    )


class TestCalcolaImportoAltriSpostamenti:
    def test_distanza_fino_a_200_km_usa_tariffa_breve(
        self, monkeypatch, nota, categoria_altro, avellino, napoli
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("100.0"), "finto"),
        )
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        importo = calcola_importo_altri_spostamenti(riga)
        assert importo == Decimal("20.00")
        assert riga.distanza_km == Decimal("100.0")
        assert riga.distanza_backend == "finto"

    def test_distanza_oltre_200_km_usa_tariffa_lunga_su_tutti_i_km(
        self, monkeypatch, nota, categoria_altro, avellino, napoli
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("250.0"), "finto"),
        )
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        importo = calcola_importo_altri_spostamenti(riga)
        assert importo == Decimal("37.50")

    def test_numero_passeggeri_ininfluente(
        self, monkeypatch, nota, categoria_altro, avellino, napoli, capo_persona
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("250.0"), "finto"),
        )
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        RigaSpesaPasseggero.objects.create(riga=riga, capo=capo_persona)
        RigaSpesaPasseggero.objects.create(riga=riga, nome_libero="Altro capo")
        importo = calcola_importo_altri_spostamenti(riga)
        assert importo == Decimal("37.50")

    def test_arrotondamento_a_due_decimali(
        self, monkeypatch, nota, categoria_altro, avellino, napoli
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("33.3"), "finto"),
        )
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        importo = calcola_importo_altri_spostamenti(riga)
        assert importo == Decimal("6.66")

    def test_distanza_gia_congelata_non_richiama_il_backend(
        self, nota, categoria_altro, avellino, napoli
    ) -> None:
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        riga.distanza_km = Decimal("50.0")
        riga.distanza_backend = "congelato"
        riga.save()
        importo = calcola_importo_altri_spostamenti(riga)
        assert importo == Decimal("10.00")

    def test_distanza_corretta_a_mano_prevale(
        self, nota, categoria_altro, avellino, napoli
    ) -> None:
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        riga.distanza_km = Decimal("50.0")
        riga.distanza_corretta_km = Decimal("40.0")
        riga.save()
        importo = calcola_importo_altri_spostamenti(riga)
        assert importo == Decimal("8.00")

    def test_senza_localita_solleva_errore(self, nota, categoria_altro) -> None:
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_altro, data=datetime.date(2027, 7, 2)
        )
        with pytest.raises(ValidationError):
            calcola_importo_altri_spostamenti(riga)

    def test_categoria_sbagliata_solleva_errore(
        self, nota, categoria_andata_ritorno, avellino, napoli
    ) -> None:
        riga = _riga_auto(nota, categoria_andata_ritorno, avellino, napoli)
        with pytest.raises(ValidationError):
            calcola_importo_altri_spostamenti(riga)


class TestCalcolaImportoAndataRitorno:
    def test_singola_riga_sotto_i_tre_occupanti(
        self, monkeypatch, nota, categoria_andata_ritorno, avellino, napoli
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("50.0"), "finto"),
        )
        andata = _riga_auto(nota, categoria_andata_ritorno, avellino, napoli)
        calcola_importo_andata_ritorno([andata])
        assert andata.importo == Decimal("10.00")

    def test_totale_andata_ritorno_supera_200_km_usa_tariffa_lunga(
        self, monkeypatch, nota, categoria_andata_ritorno, avellino, napoli
    ) -> None:
        distanze = {"andata": Decimal("120.0"), "ritorno": Decimal("110.0")}
        chiamate = iter(distanze.values())
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (next(chiamate), "finto"),
        )
        andata = _riga_auto(
            nota, categoria_andata_ritorno, avellino, napoli, datetime.date(2027, 7, 1)
        )
        ritorno = _riga_auto(
            nota, categoria_andata_ritorno, napoli, avellino, datetime.date(2027, 7, 5)
        )
        calcola_importo_andata_ritorno([andata, ritorno])
        # 230 km totali > 200: tariffa LUNGA (0.15) su tutti i km di ciascuna riga.
        assert andata.importo == Decimal("18.00")
        assert ritorno.importo == Decimal("16.50")

    def test_tre_o_piu_occupanti_sul_tratto_piu_lungo_alza_la_fascia(
        self, monkeypatch, nota, categoria_andata_ritorno, avellino, napoli, capo_persona
    ) -> None:
        distanze = iter([Decimal("50.0"), Decimal("40.0")])
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (next(distanze), "finto"),
        )
        andata = _riga_auto(
            nota, categoria_andata_ritorno, avellino, napoli, datetime.date(2027, 7, 1)
        )
        ritorno = _riga_auto(
            nota, categoria_andata_ritorno, napoli, avellino, datetime.date(2027, 7, 5)
        )
        RigaSpesaPasseggero.objects.create(riga=andata, capo=capo_persona)
        RigaSpesaPasseggero.objects.create(riga=andata, nome_libero="Altro capo")
        calcola_importo_andata_ritorno([andata, ritorno])
        # andata ha 3 occupanti (2 passeggeri + conducente) ed è il tratto più
        # lungo: fascia TRE_O_PIU (0.30) su tutte le righe, nonostante 90 km
        # totali siano sotto i 200.
        assert andata.importo == Decimal("15.00")
        assert ritorno.importo == Decimal("12.00")

    def test_parita_di_distanza_vale_il_numero_maggiore(
        self, monkeypatch, nota, categoria_andata_ritorno, avellino, napoli, capo_persona
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("50.0"), "finto"),
        )
        andata = _riga_auto(
            nota, categoria_andata_ritorno, avellino, napoli, datetime.date(2027, 7, 1)
        )
        ritorno = _riga_auto(
            nota, categoria_andata_ritorno, napoli, avellino, datetime.date(2027, 7, 5)
        )
        RigaSpesaPasseggero.objects.create(riga=ritorno, capo=capo_persona)
        RigaSpesaPasseggero.objects.create(riga=ritorno, nome_libero="Altro capo")
        calcola_importo_andata_ritorno([andata, ritorno])
        assert andata.importo == Decimal("15.00")
        assert ritorno.importo == Decimal("15.00")

    def test_categoria_sbagliata_solleva_errore(
        self, nota, categoria_altro, avellino, napoli
    ) -> None:
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        with pytest.raises(ValidationError):
            calcola_importo_andata_ritorno([riga])

    def test_lista_vuota_non_fa_nulla(self) -> None:
        calcola_importo_andata_ritorno([])


class TestCalcolaImportoRigaAutoDispatcher:
    def test_altro_salva_la_riga(
        self, monkeypatch, nota, categoria_altro, avellino, napoli
    ) -> None:
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (Decimal("100.0"), "finto"),
        )
        riga = _riga_auto(nota, categoria_altro, avellino, napoli)
        calcola_importo_riga_auto(riga)
        riga.refresh_from_db()
        assert riga.importo == Decimal("20.00")

    def test_andata_ritorno_aggrega_le_righe_gemelle_della_stessa_nota(
        self, monkeypatch, nota, categoria_andata_ritorno, avellino, napoli
    ) -> None:
        distanze = iter([Decimal("120.0"), Decimal("110.0")])
        monkeypatch.setattr(
            calcolo_riga_auto,
            "distanza_km_tra_localita",
            lambda p, a: (next(distanze), "finto"),
        )
        andata = _riga_auto(
            nota, categoria_andata_ritorno, avellino, napoli, datetime.date(2027, 7, 1)
        )
        ritorno = _riga_auto(
            nota, categoria_andata_ritorno, napoli, avellino, datetime.date(2027, 7, 5)
        )
        calcola_importo_riga_auto(ritorno)
        andata.refresh_from_db()
        ritorno.refresh_from_db()
        assert andata.importo == Decimal("18.00")
        assert ritorno.importo == Decimal("16.50")

    def test_categoria_non_chilometrica_solleva_errore(self, nota) -> None:
        categoria_documentale = CategoriaSpesa.objects.create(nome="Vitto test dispatcher")
        riga = RigaSpesa.objects.create(
            nota=nota, categoria=categoria_documentale, data=datetime.date(2027, 7, 2)
        )
        with pytest.raises(ValidationError):
            calcola_importo_riga_auto(riga)
