"""Riattribuzione delle partecipazioni ai trasferimenti (D-29), agganciata via
segnale su TrasferimentoCapo."""

import datetime
import io
from decimal import Decimal

import pytest
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile

from apps.anagrafica.importazione import applica_piano, costruisci_piano
from apps.anagrafica.models import Capo, CensimentoCapo, TrasferimentoCapo
from apps.anagrafica.parser.buonacaccia import parse_csv
from apps.contributi.models import Campagna, Partecipazione, StatoCampagna, TipologiaCampo
from apps.contributi.trasferimenti import riattribuisci_partecipazioni
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026

HEADER = (
    "ANNO SCOUT,CODICE SOCIO,NOME,COGNOME,SESSO,DATA NASCITA,COMUNE NASCITA,"
    "CODICE FISCALE,NAZIONALITA,INDIRIZZO,CIVICO,COMUNE RESIDENZA,"
    "PROVINCIA RESIDENZA,CAP,EMAIL,CELLULARE,PROFESSIONE,LIVELLO FOCA,"
    "INGRESSO COCA,COMUNITA SOCIO,STATUS SOCIO,GRUPPO,ORDINALE,EMAIL GRUPPO,"
    "INDIRIZZO GRUPPO,CIVICO GRUPPO,CAP GRUPPO,RESIDENZA GRUPPO,"
    "PROVINCIA GRUPPO,TELEFONO GRUPPO,CODICE FISCALE GRUPPO,PARROCCHIA GRUPPO,"
    "DIOCESI GRUPPO,DENOM. SOCIALE GRUPPO"
)


def _riga_csv(*, ordinale, gruppo_nome, email_gruppo) -> str:
    campi = [
        '="2026"',
        '="10001"',
        '="MARIO"',
        '="ROSSI"',
        '="M"',
        "01/01/1980",
        '="AVELLINO"',
        '="RSSMRA80A01A509X"',
        '="ITALIA"',
        '="VIA ROMA"',
        '="1"',
        '="AVELLINO"',
        '="AV"',
        '="83100"',
        '="socio@example.org"',
        '="3331234567"',
        '="IMPIEGATO"',
        '="3"',
        '="2010"',
        '="CLAN"',
        '="RINNOVO ADESIONE"',
        f'="{gruppo_nome}"',
        f'="{ordinale}"',
        f'="{email_gruppo}"',
        '="VIA GRUPPO"',
        '="2"',
        '="83100"',
        '="AVELLINO"',
        '="AV"',
        '="0825000000"',
        '="00000000000"',
        '="SAN MODESTINO"',
        '="AVELLINO"',
        f'="AGESCI {gruppo_nome}"',
        "",
    ]
    return ",".join(campi)


def _csv_testo(riga: str) -> str:
    return "sep=,\n" + HEADER + "\n" + riga + "\n"


@pytest.fixture
def gruppo_a() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def gruppo_b() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def capo(gruppo_a) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo_a)
    return c


@pytest.fixture
def campagna() -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


@pytest.fixture
def tipologia() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


def _partecipazione(campagna, capo, gruppo, tipologia) -> Partecipazione:
    p = Partecipazione(
        campagna=campagna,
        capo=capo,
        gruppo=gruppo,
        tipologia=tipologia,
        data_inizio=datetime.date(2026, 6, 1),
        data_fine=datetime.date(2026, 6, 8),
        luogo="Base scout",
        quota_versata=Decimal("51.50"),
    )
    p.full_clean(exclude=["stato"])
    p.save()
    return p


class TestRiattribuisciPartecipazioni:
    """Test isolato della funzione, senza passare dalla pipeline CSV
    completa: il segnale post_save è disconnesso qui, perché
    TrasferimentoCapo.objects.create() lo innescherebbe comunque
    automaticamente (apps/contributi/apps.py::ready()), rendendo ridondante
    la chiamata diretta a riattribuisci_partecipazioni() sottostante."""

    @pytest.fixture(autouse=True)
    def _senza_segnale(self):
        from django.db.models.signals import post_save

        from apps.contributi.trasferimenti import su_trasferimento_capo

        post_save.disconnect(
            su_trasferimento_capo,
            sender=TrasferimentoCapo,
            dispatch_uid="contributi_riattribuzione_trasferimento",
        )
        yield
        post_save.connect(
            su_trasferimento_capo,
            sender=TrasferimentoCapo,
            dispatch_uid="contributi_riattribuzione_trasferimento",
        )

    def test_sposta_il_gruppo_e_traccia_in_auditlog(
        self, capo, gruppo_a, gruppo_b, campagna, tipologia
    ):
        partecipazione = _partecipazione(campagna, capo, gruppo_a, tipologia)
        trasferimento = TrasferimentoCapo.objects.create(
            capo=capo, anno_scout=ANNO, gruppo_origine=gruppo_a, gruppo_destino=gruppo_b
        )

        interessate = riattribuisci_partecipazioni(trasferimento)

        partecipazione.refresh_from_db()
        assert partecipazione.gruppo_id == gruppo_b.codice
        assert interessate == [partecipazione]

        ct = ContentType.objects.get_for_model(Partecipazione)
        log = LogEntry.objects.filter(content_type=ct, object_id=str(partecipazione.pk)).latest(
            "timestamp"
        )
        assert log.changes["gruppo"] == [gruppo_a.codice, gruppo_b.codice]

    def test_campagna_liquidata_non_toccata(self, capo, gruppo_a, gruppo_b, campagna, tipologia):
        partecipazione = _partecipazione(campagna, capo, gruppo_a, tipologia)
        Campagna.objects.filter(pk=campagna.pk).update(stato=StatoCampagna.LIQUIDATA)
        trasferimento = TrasferimentoCapo.objects.create(
            capo=capo, anno_scout=ANNO, gruppo_origine=gruppo_a, gruppo_destino=gruppo_b
        )

        interessate = riattribuisci_partecipazioni(trasferimento)

        partecipazione.refresh_from_db()
        assert partecipazione.gruppo_id == gruppo_a.codice
        assert interessate == []

    def test_tocca_solo_le_partecipazioni_del_gruppo_origine(
        self, capo, gruppo_a, gruppo_b, campagna, tipologia
    ):
        altro_capo = Capo.objects.create(codice_socio="20002", nome="LUCA", cognome="BIANCHI")
        CensimentoCapo.objects.create(capo=altro_capo, anno_scout=ANNO, gruppo=gruppo_b)
        partecipazione_altro_capo = _partecipazione(campagna, altro_capo, gruppo_b, tipologia)

        trasferimento = TrasferimentoCapo.objects.create(
            capo=capo, anno_scout=ANNO, gruppo_origine=gruppo_a, gruppo_destino=gruppo_b
        )
        riattribuisci_partecipazioni(trasferimento)

        partecipazione_altro_capo.refresh_from_db()
        assert partecipazione_altro_capo.gruppo_id == gruppo_b.codice  # invariata


class TestSegnalePostSaveImportCSV:
    def test_import_csv_rileva_trasferimento_e_riattribuisce(
        self, capo, gruppo_a, gruppo_b, campagna, tipologia
    ):
        partecipazione = _partecipazione(campagna, capo, gruppo_a, tipologia)

        testo = _csv_testo(
            _riga_csv(
                ordinale="E0134",
                gruppo_nome="AVELLINO 2",
                email_gruppo="avellino2@campania.agesci.it",
            )
        )
        risultato = parse_csv(io.StringIO(testo))
        piano = costruisci_piano(risultato)
        file_originale = ContentFile(testo.encode("utf-8-sig"), name="ricercasoci.csv")
        applica_piano(piano, file_originale=file_originale, utente=None)

        partecipazione.refresh_from_db()
        assert partecipazione.gruppo_id == gruppo_b.codice
        assert TrasferimentoCapo.objects.filter(capo=capo, gruppo_destino=gruppo_b).exists()
