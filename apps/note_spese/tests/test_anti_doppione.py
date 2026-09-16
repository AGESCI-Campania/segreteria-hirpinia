"""D-57: segnalazioni anti-doppione (mai un blocco)."""

import datetime
from decimal import Decimal

import pytest

from apps.anagrafica.models import Capo
from apps.note_spese.anti_doppione import (
    segnalazioni_passeggero_con_propria_riga,
    segnalazioni_targa_sovrapposta,
)
from apps.note_spese.models import (
    CategoriaSpesa,
    Evento,
    Localita,
    NotaSpese,
    RigaSpesa,
    RigaSpesaPasseggero,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def altro_evento() -> Evento:
    return Evento.objects.create(nome="Altro campo 2027", data_inizio=datetime.date(2027, 8, 1))


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
        nome="Avellino test", latitudine=Decimal("40.913637"), longitudine=Decimal("14.790168")
    )


@pytest.fixture
def napoli() -> Localita:
    return Localita.objects.create(
        nome="Napoli test", latitudine=Decimal("40.851775"), longitudine=Decimal("14.268121")
    )


@pytest.fixture
def guidatore() -> Capo:
    return Capo.objects.create(codice_socio="111111A", nome="Mario", cognome="Rossi")


@pytest.fixture
def passeggero_capo() -> Capo:
    return Capo.objects.create(codice_socio="222222B", nome="Luigi", cognome="Bianchi")


def _nota(gruppo, evento, beneficiario) -> NotaSpese:
    return NotaSpese.objects.create(
        beneficiario=beneficiario, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )


class TestSegnalazioniPasseggeroConPropriaRiga:
    def test_passeggero_con_propria_riga_stessa_tratta_evento_e_segnalato(
        self, gruppo, evento, categoria_altro, avellino, napoli, guidatore, passeggero_capo
    ) -> None:
        nota_guidatore = _nota(gruppo, evento, guidatore)
        riga_guidatore = RigaSpesa.objects.create(
            nota=nota_guidatore,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )
        RigaSpesaPasseggero.objects.create(riga=riga_guidatore, capo=passeggero_capo)

        nota_passeggero = _nota(gruppo, evento, passeggero_capo)
        riga_passeggero = RigaSpesa.objects.create(
            nota=nota_passeggero,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )

        segnalazioni = segnalazioni_passeggero_con_propria_riga(riga_guidatore)

        assert len(segnalazioni) == 1
        assert segnalazioni[0].riga_del_passeggero == riga_passeggero

    def test_tratta_diversa_non_e_segnalata(
        self, gruppo, evento, categoria_altro, avellino, napoli, guidatore, passeggero_capo
    ) -> None:
        nota_guidatore = _nota(gruppo, evento, guidatore)
        riga_guidatore = RigaSpesa.objects.create(
            nota=nota_guidatore,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )
        RigaSpesaPasseggero.objects.create(riga=riga_guidatore, capo=passeggero_capo)

        altra_localita = Localita.objects.create(
            nome="Salerno test", latitudine=Decimal("40.674004"), longitudine=Decimal("14.759138")
        )
        nota_passeggero = _nota(gruppo, evento, passeggero_capo)
        RigaSpesa.objects.create(
            nota=nota_passeggero,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=altra_localita,
        )

        assert segnalazioni_passeggero_con_propria_riga(riga_guidatore) == []

    def test_evento_diverso_non_e_segnalato(
        self,
        gruppo,
        evento,
        altro_evento,
        categoria_altro,
        avellino,
        napoli,
        guidatore,
        passeggero_capo,
    ) -> None:
        nota_guidatore = _nota(gruppo, evento, guidatore)
        riga_guidatore = RigaSpesa.objects.create(
            nota=nota_guidatore,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )
        RigaSpesaPasseggero.objects.create(riga=riga_guidatore, capo=passeggero_capo)

        nota_passeggero = _nota(gruppo, altro_evento, passeggero_capo)
        RigaSpesa.objects.create(
            nota=nota_passeggero,
            categoria=categoria_altro,
            data=datetime.date(2027, 8, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )

        assert segnalazioni_passeggero_con_propria_riga(riga_guidatore) == []

    def test_passeggero_a_nome_libero_non_genera_crash_ne_segnalazione(
        self, gruppo, evento, categoria_altro, avellino, napoli, guidatore
    ) -> None:
        nota_guidatore = _nota(gruppo, evento, guidatore)
        riga_guidatore = RigaSpesa.objects.create(
            nota=nota_guidatore,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )
        RigaSpesaPasseggero.objects.create(riga=riga_guidatore, nome_libero="Un capo qualsiasi")

        assert segnalazioni_passeggero_con_propria_riga(riga_guidatore) == []


class TestSegnalazioniTargaSovrapposta:
    def test_stessa_targa_date_sovrapposte_e_segnalata(
        self, gruppo, evento, categoria_altro, avellino, napoli, guidatore, passeggero_capo
    ) -> None:
        nota_a = _nota(gruppo, evento, guidatore)
        riga_a = RigaSpesa.objects.create(
            nota=nota_a,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 5),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )
        nota_b = _nota(gruppo, evento, passeggero_capo)
        riga_b = RigaSpesa.objects.create(
            nota=nota_b,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 5),
            localita_partenza=napoli,
            localita_arrivo=avellino,
            targa="AB123CD",
        )

        segnalazioni = segnalazioni_targa_sovrapposta(riga_a)

        assert len(segnalazioni) == 1
        assert segnalazioni[0].altra_riga == riga_b

    def test_stessa_targa_date_non_sovrapposte_non_e_segnalata(
        self, gruppo, evento, categoria_altro, avellino, napoli, guidatore, passeggero_capo
    ) -> None:
        nota_a = _nota(gruppo, evento, guidatore)
        riga_a = RigaSpesa.objects.create(
            nota=nota_a,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 5),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )
        nota_b = _nota(gruppo, evento, passeggero_capo)
        RigaSpesa.objects.create(
            nota=nota_b,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 20),
            localita_partenza=napoli,
            localita_arrivo=avellino,
            targa="AB123CD",
        )

        assert segnalazioni_targa_sovrapposta(riga_a) == []

    def test_stessa_nota_non_si_autosegnala(
        self, gruppo, evento, categoria_andata_ritorno, avellino, napoli, guidatore
    ) -> None:
        nota = _nota(gruppo, evento, guidatore)
        andata = RigaSpesa.objects.create(
            nota=nota,
            categoria=categoria_andata_ritorno,
            data=datetime.date(2027, 7, 1),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )
        RigaSpesa.objects.create(
            nota=nota,
            categoria=categoria_andata_ritorno,
            data=datetime.date(2027, 7, 10),
            localita_partenza=napoli,
            localita_arrivo=avellino,
            targa="AB123CD",
        )

        assert segnalazioni_targa_sovrapposta(andata) == []

    def test_intervallo_andata_ritorno_copre_tutto_il_viaggio(
        self,
        gruppo,
        evento,
        categoria_andata_ritorno,
        categoria_altro,
        avellino,
        napoli,
        guidatore,
        passeggero_capo,
    ) -> None:
        nota_viaggio = _nota(gruppo, evento, guidatore)
        andata = RigaSpesa.objects.create(
            nota=nota_viaggio,
            categoria=categoria_andata_ritorno,
            data=datetime.date(2027, 7, 1),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )
        RigaSpesa.objects.create(
            nota=nota_viaggio,
            categoria=categoria_andata_ritorno,
            data=datetime.date(2027, 7, 10),
            localita_partenza=napoli,
            localita_arrivo=avellino,
            targa="AB123CD",
        )

        nota_intermedia = _nota(gruppo, evento, passeggero_capo)
        riga_intermedia = RigaSpesa.objects.create(
            nota=nota_intermedia,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 5),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )

        segnalazioni = segnalazioni_targa_sovrapposta(andata)

        assert riga_intermedia in {s.altra_riga for s in segnalazioni}

    def test_targa_vuota_non_genera_segnalazioni(
        self, gruppo, evento, categoria_altro, avellino, napoli, guidatore
    ) -> None:
        nota = _nota(gruppo, evento, guidatore)
        riga = RigaSpesa.objects.create(
            nota=nota,
            categoria=categoria_altro,
            data=datetime.date(2027, 7, 5),
            localita_partenza=avellino,
            localita_arrivo=napoli,
        )
        assert segnalazioni_targa_sovrapposta(riga) == []
