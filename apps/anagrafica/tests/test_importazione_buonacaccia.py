"""Test di integrazione dell'import CSV Buona Caccia (D-22, D-29, D-34): CSV
sintetici inline, nessuna fixture reale."""

import io

import pytest
from django.core.files.base import ContentFile

from apps.anagrafica.importazione import applica_piano, costruisci_piano
from apps.anagrafica.models import Capo, CensimentoCapo, ImportazioneCSV, TrasferimentoCapo
from apps.anagrafica.parser.buonacaccia import parse_csv
from apps.organizzazione.models import AllowlistGruppo, Gruppo, Origine

pytestmark = pytest.mark.django_db

HEADER = (
    "ANNO SCOUT,CODICE SOCIO,NOME,COGNOME,SESSO,DATA NASCITA,COMUNE NASCITA,"
    "CODICE FISCALE,NAZIONALITA,INDIRIZZO,CIVICO,COMUNE RESIDENZA,"
    "PROVINCIA RESIDENZA,CAP,EMAIL,CELLULARE,PROFESSIONE,LIVELLO FOCA,"
    "INGRESSO COCA,COMUNITA SOCIO,STATUS SOCIO,GRUPPO,ORDINALE,EMAIL GRUPPO,"
    "INDIRIZZO GRUPPO,CIVICO GRUPPO,CAP GRUPPO,RESIDENZA GRUPPO,"
    "PROVINCIA GRUPPO,TELEFONO GRUPPO,CODICE FISCALE GRUPPO,PARROCCHIA GRUPPO,"
    "DIOCESI GRUPPO,DENOM. SOCIALE GRUPPO"
)


def _riga(
    *,
    anno="2026",
    codice_socio="10001",
    nome="MARIO",
    cognome="ROSSI",
    data_nascita="01/01/1980",
    ordinale="E0133",
    gruppo_nome="AVELLINO 1",
    email_gruppo="avellino1@campania.agesci.it",
    status_socio="RINNOVO ADESIONE",
) -> str:
    campi = [
        f'="{anno}"' if anno else "",
        f'="{codice_socio}"' if codice_socio else "",
        f'="{nome}"',
        f'="{cognome}"',
        '="M"',
        data_nascita,
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
        f'="{status_socio}"',
        f'="{gruppo_nome}"',
        f'="{ordinale}"' if ordinale else "",
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


def _csv_testo(*righe: str) -> str:
    return "sep=,\n" + HEADER + "\n" + "\n".join(righe) + "\n"


def _importa(testo_csv: str) -> ImportazioneCSV:
    risultato = parse_csv(io.StringIO(testo_csv))
    piano = costruisci_piano(risultato)
    file_originale = ContentFile(testo_csv.encode("utf-8-sig"), name="ricercasoci.csv")
    return applica_piano(piano, file_originale=file_originale, utente=None)


class TestImportIniziale:
    def test_crea_gruppo_capo_e_censimento(self):
        importazione = _importa(_csv_testo(_riga()))

        assert importazione.anno_scout == 2026
        assert importazione.conteggi["gruppi_creati"] == 1
        assert importazione.conteggi["capi_creati"] == 1
        assert importazione.conteggi["censimenti_creati"] == 1

        gruppo = Gruppo.objects.get(codice="E0133")
        assert gruppo.nome == "AVELLINO 1"
        assert gruppo.origine == Origine.IMPORT

        capo = Capo.objects.get(codice_socio="10001")
        assert capo.cognome == "ROSSI"
        assert capo.attivo is True

        censimento = CensimentoCapo.objects.get(capo=capo, anno_scout=2026)
        assert censimento.gruppo_id == "E0133"
        assert censimento.a_disposizione is True
        assert censimento.is_capogruppo is False

    def test_idempotenza(self):
        testo = _csv_testo(_riga())
        _importa(testo)
        seconda = _importa(testo)

        assert seconda.conteggi["gruppi_creati"] == 0
        assert seconda.conteggi["capi_creati"] == 0
        assert seconda.conteggi["censimenti_creati"] == 0
        assert Capo.objects.count() == 1
        assert CensimentoCapo.objects.count() == 1
        assert Gruppo.objects.filter(codice="E0133").count() == 1


class TestGruppoOrigine:
    def test_gruppo_nuovo_ha_origine_import(self):
        _importa(_csv_testo(_riga()))
        assert Gruppo.objects.get(codice="E0133").origine == Origine.IMPORT

    def test_gruppo_manuale_esistente_non_sovrascritto(self):
        Gruppo.objects.create(codice="E0133", nome="AVELLINO 1", origine=Origine.MANUALE)
        _importa(_csv_testo(_riga(gruppo_nome="AVELLINO 1 BIS")))

        gruppo = Gruppo.objects.get(codice="E0133")
        assert gruppo.origine == Origine.MANUALE
        assert gruppo.nome == "AVELLINO 1 BIS"  # gli altri campi si aggiornano comunque


class TestDisattivazioneERiattivazione:
    def test_capo_assente_viene_disattivato(self):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        assente = Capo.objects.create(codice_socio="99999", nome="LUIGI", cognome="VERDI")
        CensimentoCapo.objects.create(capo=assente, anno_scout=2026, gruppo=gruppo)

        importazione = _importa(_csv_testo(_riga(codice_socio="10001")))

        assente.refresh_from_db()
        assert assente.attivo is False
        assert assente.data_disattivazione is not None
        assert importazione.capi_disattivati.filter(pk="99999").exists()

    def test_capo_riattivato_se_ricompare(self):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        import datetime

        capo = Capo.objects.create(
            codice_socio="10001",
            nome="MARIO",
            cognome="ROSSI",
            attivo=False,
            data_disattivazione=datetime.date(2025, 6, 1),
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2025, gruppo=gruppo)

        importazione = _importa(_csv_testo(_riga(codice_socio="10001")))

        capo.refresh_from_db()
        assert capo.attivo is True
        assert capo.data_disattivazione is None
        assert importazione.capi_riattivati.filter(pk="10001").exists()

    def test_import_parziale_non_tocca_gruppi_assenti_dal_file(self):
        gruppo_x = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        capo_x = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        CensimentoCapo.objects.create(capo=capo_x, anno_scout=2026, gruppo=gruppo_x)

        # Il file importato riguarda solo un altro gruppo (E0134): nessuna riga
        # per E0133, quindi capo_x resta invariato.
        _importa(
            _csv_testo(_riga(codice_socio="20002", ordinale="E0134", gruppo_nome="AVELLINO 2"))
        )

        capo_x.refresh_from_db()
        assert capo_x.attivo is True


class TestTrasferimento:
    def test_cambio_gruppo_crea_censimento_aggiornato_e_registro(self):
        gruppo_origine = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        CensimentoCapo.objects.create(capo=capo, anno_scout=2025, gruppo=gruppo_origine)

        importazione = _importa(
            _csv_testo(
                _riga(
                    codice_socio="10001",
                    ordinale="E0134",
                    gruppo_nome="AVELLINO 2",
                    email_gruppo="avellino2@campania.agesci.it",
                )
            )
        )

        censimento = CensimentoCapo.objects.get(capo=capo, anno_scout=2026)
        assert censimento.gruppo_id == "E0134"

        trasferimento = TrasferimentoCapo.objects.get(capo=capo)
        assert trasferimento.gruppo_origine_id == "E0133"
        assert trasferimento.gruppo_destino_id == "E0134"
        assert trasferimento.anno_scout == 2026
        assert trasferimento.importazione_id == importazione.pk
        assert importazione.conteggi["trasferimenti_rilevati"] == 1


class TestAllowlist:
    def test_email_gruppo_popola_allowlist(self):
        _importa(_csv_testo(_riga()))
        voce = AllowlistGruppo.objects.get(email="avellino1@campania.agesci.it")
        assert voce.codice_gruppo == "E0133"
        assert voce.origine == Origine.IMPORT

    def test_e9001_non_tocca_allowlist(self):
        prima = set(AllowlistGruppo.objects.values_list("email", flat=True))

        _importa(
            _csv_testo(
                _riga(
                    codice_socio="30003",
                    ordinale="E9001",
                    gruppo_nome="COM ZONA HIRPINIA",
                    email_gruppo="zonahirpinia@campania.agesci.it",
                )
            )
        )

        dopo = set(AllowlistGruppo.objects.values_list("email", flat=True))
        assert dopo == prima  # invariata: nessuna voce aggiunta per E9001
        assert not AllowlistGruppo.objects.filter(email="zonahirpinia@campania.agesci.it").exists()


class TestAnomalie:
    def test_codice_socio_mancante_e_anomalia_bloccante_non_scrive_nulla(self):
        importazione = _importa(_csv_testo(_riga(codice_socio="")))

        assert Capo.objects.count() == 0
        assert importazione.conteggi["anomalie_bloccanti"] == 1
        assert any(a["campo"] == "CODICE SOCIO" for a in importazione.anomalie)

    def test_data_nascita_malformata_e_avviso_non_bloccante(self):
        importazione = _importa(_csv_testo(_riga(data_nascita="non-una-data")))

        capo = Capo.objects.get(codice_socio="10001")
        assert capo.data_nascita is None
        assert importazione.conteggi["avvisi"] >= 1
        assert any(a["campo"] == "DATA NASCITA" for a in importazione.anomalie)

    def test_ordinale_ambiguo_non_scrive_censimento(self):
        importazione = _importa(
            _csv_testo(
                _riga(codice_socio="40004", ordinale="E0133"),
                _riga(codice_socio="40004", ordinale="E0134", gruppo_nome="AVELLINO 2"),
            )
        )

        assert not CensimentoCapo.objects.filter(capo_id="40004").exists()
        assert importazione.conteggi["anomalie_bloccanti"] == 2
