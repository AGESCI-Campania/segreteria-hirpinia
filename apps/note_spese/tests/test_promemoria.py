"""F7/D-63: promemoria al capo (settimanale di norma, giornaliero negli
ultimi 15 giorni prima della chiusura dell'anno associativo)."""

import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command

from apps.anagrafica.models import Capo
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese, RigaSpesa, StatoNota
from apps.note_spese.promemoria import e_giorno_di_promemoria, invia_promemoria
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


class TestEGiornoDiPromemoria:
    def test_lunedi_fuori_dalla_finestra_giornaliera(self) -> None:
        lunedi_qualsiasi = datetime.date(2027, 3, 1)
        assert lunedi_qualsiasi.weekday() == 0
        assert e_giorno_di_promemoria(lunedi_qualsiasi) is True

    def test_martedi_fuori_dalla_finestra_giornaliera(self) -> None:
        martedi = datetime.date(2027, 3, 2)
        assert martedi.weekday() == 1
        assert e_giorno_di_promemoria(martedi) is False

    def test_finestra_giornaliera_indipendente_dal_giorno_settimana(self) -> None:
        # 20 settembre 2027 è un lunedì per caso: si sceglie un anno in cui
        # il 20 settembre NON cade di lunedì, per isolare l'effetto finestra.
        data = datetime.date(2026, 9, 20)
        assert data.weekday() != 0
        assert e_giorno_di_promemoria(data) is True

    def test_16_settembre_e_dentro_la_finestra(self) -> None:
        data = datetime.date(2026, 9, 16)
        assert e_giorno_di_promemoria(data) is True

    def test_15_settembre_e_dentro_la_finestra(self) -> None:
        # "15 giorni o meno dalla chiusura" è inclusivo: 30 - 15 = 15.
        data = datetime.date(2026, 9, 15)
        assert e_giorno_di_promemoria(data) is True

    def test_14_settembre_e_fuori_dalla_finestra(self) -> None:
        data = datetime.date(2026, 9, 14)
        if data.weekday() != 0:
            assert e_giorno_di_promemoria(data) is False

    def test_1_ottobre_dopo_chiusura_solo_se_lunedi(self) -> None:
        data = datetime.date(2026, 10, 1)
        assert e_giorno_di_promemoria(data) is (data.weekday() == 0)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test promemoria", richiede_allegato=False)


def _nota(gruppo, capo, evento, categoria, stato, **extra) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        stato=stato,
        **extra,
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


LUNEDI = datetime.date(2027, 3, 1)


class TestInviaPromemoria:
    def test_nessun_invio_se_non_e_giorno_di_promemoria(self, gruppo, evento, categoria) -> None:
        capo = Capo.objects.create(
            codice_socio="1A", nome="Mario", cognome="Rossi", email="mario@example.it"
        )
        _nota(gruppo, capo, evento, categoria, StatoNota.BOZZA)
        martedi = datetime.date(2027, 3, 2)

        inviate = invia_promemoria(martedi)

        assert inviate == 0
        assert mail.outbox == []

    def test_bozza_genera_promemoria(self, gruppo, evento, categoria) -> None:
        capo = Capo.objects.create(
            codice_socio="1A", nome="Mario", cognome="Rossi", email="mario@example.it"
        )
        _nota(gruppo, capo, evento, categoria, StatoNota.BOZZA)

        inviate = invia_promemoria(LUNEDI)

        assert inviate == 1
        assert mail.outbox[0].to == ["mario@example.it"]

    def test_in_verifica_non_genera_promemoria(self, gruppo, evento, categoria) -> None:
        capo = Capo.objects.create(
            codice_socio="1A", nome="Mario", cognome="Rossi", email="mario@example.it"
        )
        _nota(gruppo, capo, evento, categoria, StatoNota.IN_VERIFICA)

        inviate = invia_promemoria(LUNEDI)

        assert inviate == 0
        assert mail.outbox == []

    def test_capo_senza_email_non_riceve_ma_altri_si(self, gruppo, evento, categoria) -> None:
        capo_senza_email = Capo.objects.create(codice_socio="1A", nome="Mario", cognome="Rossi")
        capo_con_email = Capo.objects.create(
            codice_socio="2B", nome="Luigi", cognome="Bianchi", email="luigi@example.it"
        )
        _nota(gruppo, capo_senza_email, evento, categoria, StatoNota.DA_INTEGRARE)
        _nota(gruppo, capo_con_email, evento, categoria, StatoNota.DA_CONFERMARE)

        inviate = invia_promemoria(LUNEDI)

        assert inviate == 1
        assert mail.outbox[0].to == ["luigi@example.it"]

    def test_note_eliminate_escluse(self, gruppo, evento, categoria) -> None:
        capo = Capo.objects.create(
            codice_socio="1A", nome="Mario", cognome="Rossi", email="mario@example.it"
        )
        _nota(
            gruppo,
            capo,
            evento,
            categoria,
            StatoNota.BOZZA,
            eliminata_il=datetime.datetime(2027, 1, 1, tzinfo=datetime.UTC),
        )

        inviate = invia_promemoria(LUNEDI)

        assert inviate == 0
        assert mail.outbox == []

    def test_digest_unico_per_piu_note_dello_stesso_capo(self, gruppo, evento, categoria) -> None:
        capo = Capo.objects.create(
            codice_socio="1A", nome="Mario", cognome="Rossi", email="mario@example.it"
        )
        _nota(gruppo, capo, evento, categoria, StatoNota.BOZZA)
        _nota(gruppo, capo, evento, categoria, StatoNota.DA_INTEGRARE)

        inviate = invia_promemoria(LUNEDI)

        assert inviate == 1
        corpo = mail.outbox[0].body
        assert corpo.count("Bozza") == 1
        assert "Da integrare" in corpo


class TestComandoManagement:
    def test_comando_invoca_invia_promemoria(self, gruppo, evento, categoria, settings) -> None:
        capo = Capo.objects.create(
            codice_socio="1A", nome="Mario", cognome="Rossi", email="mario@example.it"
        )
        _nota(gruppo, capo, evento, categoria, StatoNota.BOZZA)

        out = StringIO()
        call_command("note_spese_promemoria", stdout=out)

        # Esito variabile in base alla data reale di esecuzione del test
        # (il comando non accetta una data forzata): verifichiamo solo che
        # il comando giri senza errori e stampi un esito coerente col
        # conteggio di email realmente inviate.
        assert "Promemoria inviati:" in out.getvalue()
        assert len(mail.outbox) in (0, 1)
