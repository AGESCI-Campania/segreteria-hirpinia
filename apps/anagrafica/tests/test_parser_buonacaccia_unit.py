"""Unit test del parser CSV Buona Caccia: solo CSV sintetici inline, nessuna
fixture reale (i dati anagrafici non vanno versionati)."""

import io

from apps.anagrafica.parser.buonacaccia import AVVISO, ERRORE, parse_csv

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
    sesso="M",
    data_nascita="01/01/1980",
    ordinale="E0133",
    livello_foca="3",
    status_socio="RINNOVO ADESIONE",
) -> str:
    campi = [
        f'="{anno}"',
        f'="{codice_socio}"',
        f'="{nome}"',
        f'="{cognome}"',
        f'="{sesso}"',
        data_nascita,  # nuda, mai wrappata
        '="AVELLINO"',
        '="RSSMRA80A01A509X"',
        '="ITALIA"',
        '="VIA ROMA"',
        '="1"',
        '="AVELLINO"',
        '="AV"',
        '="83100"',
        '="mario.rossi@example.org"',
        '="3331234567"',
        '="IMPIEGATO"',
        f'="{livello_foca}"',
        '="2010"',
        '="CLAN"',
        f'="{status_socio}"',
        '="AVELLINO 1"',
        f'="{ordinale}"',
        '="avellino1@campania.agesci.it"',
        '="VIA GRUPPO"',
        '="2"',
        '="83100"',
        '="AVELLINO"',
        '="AV"',
        '="0825000000"',
        '="00000000000"',
        '="SAN MODESTINO"',
        '="AVELLINO"',
        '="AGESCI AVELLINO 1"',
        "",  # virgola finale: eccedenza gestita da restkey
    ]
    return ",".join(campi)


def _csv(*righe: str, header: str = HEADER) -> io.StringIO:
    testo = "sep=,\n" + header + "\n" + "\n".join(righe) + "\n"
    return io.StringIO(testo)


class TestRigaValida:
    def test_campi_spogliati_correttamente(self):
        risultato = parse_csv(_csv(_riga()))
        assert risultato.anno_scout == 2026
        assert len(risultato.righe) == 1
        riga = risultato.righe[0]
        assert riga.codice_socio == "10001"
        assert riga.nome == "MARIO"
        assert riga.cognome == "ROSSI"
        assert riga.ordinale == "E0133"
        assert riga.email == "mario.rossi@example.org"
        assert riga.anomalie == []

    def test_data_nascita_nuda_parsata(self):
        risultato = parse_csv(_csv(_riga(data_nascita="25/02/1981")))
        assert risultato.righe[0].data_nascita.isoformat() == "1981-02-25"

    def test_nessuna_anomalia_file(self):
        risultato = parse_csv(_csv(_riga()))
        assert risultato.anomalie == []
        assert risultato.anomalie_file == []


class TestAnomalieBloccanti:
    def test_codice_socio_mancante_riga_scartata(self):
        risultato = parse_csv(_csv(_riga(codice_socio="")))
        assert risultato.righe == []
        assert len(risultato.anomalie) == 1
        assert risultato.anomalie[0].livello == ERRORE
        assert risultato.anomalie[0].campo == "CODICE SOCIO"

    def test_ordinale_malformato_riga_scartata(self):
        risultato = parse_csv(_csv(_riga(ordinale="X123")))
        assert risultato.righe == []
        assert risultato.anomalie[0].livello == ERRORE
        assert risultato.anomalie[0].campo == "ORDINALE"

    def test_ordinale_vuoto_riga_scartata(self):
        risultato = parse_csv(_csv(_riga(ordinale="")))
        assert risultato.righe == []
        assert risultato.anomalie[0].campo == "ORDINALE"

    def test_stesso_socio_ordinali_diversi_entrambe_scartate(self):
        risultato = parse_csv(
            _csv(
                _riga(codice_socio="20002", ordinale="E0133"),
                _riga(codice_socio="20002", ordinale="E0134"),
            )
        )
        assert risultato.righe == []
        errori_ordinale = [a for a in risultato.anomalie if a.campo == "ORDINALE"]
        assert len(errori_ordinale) == 2
        assert all(a.livello == ERRORE for a in errori_ordinale)


class TestAnomalieNonBloccanti:
    def test_data_nascita_malformata_riga_comunque_presente(self):
        risultato = parse_csv(_csv(_riga(data_nascita="non-una-data")))
        assert len(risultato.righe) == 1
        assert risultato.righe[0].data_nascita is None
        assert any(a.campo == "DATA NASCITA" and a.livello == AVVISO for a in risultato.anomalie)

    def test_livello_foca_non_intero_riga_comunque_presente(self):
        risultato = parse_csv(_csv(_riga(livello_foca="alto")))
        assert len(risultato.righe) == 1
        assert risultato.righe[0].livello_foca is None
        assert any(a.campo == "LIVELLO FOCA" and a.livello == AVVISO for a in risultato.anomalie)

    def test_status_socio_ignoto_e_avviso_non_bloccante(self):
        risultato = parse_csv(_csv(_riga(status_socio="TRASFERIMENTO")))
        assert len(risultato.righe) == 1
        assert any(a.campo == "STATUS SOCIO" and a.livello == AVVISO for a in risultato.anomalie)


class TestAnomalieFile:
    def test_prima_riga_diversa_da_sep_e_anomalia_bloccante(self):
        testo = HEADER + "\n" + _riga() + "\n"
        risultato = parse_csv(io.StringIO(testo))
        assert risultato.anno_scout is None
        assert risultato.righe == []
        assert risultato.anomalie_file

    def test_anno_scout_incoerente_interrompe_il_parsing(self):
        risultato = parse_csv(
            _csv(
                _riga(codice_socio="1", anno="2026"),
                _riga(codice_socio="2", anno="2027"),
            )
        )
        assert risultato.anno_scout is None
        assert risultato.righe == []
        assert risultato.anomalie_file

    def test_file_vuoto_di_righe_dati(self):
        risultato = parse_csv(_csv())
        assert risultato.anno_scout is None
        assert risultato.anomalie_file
