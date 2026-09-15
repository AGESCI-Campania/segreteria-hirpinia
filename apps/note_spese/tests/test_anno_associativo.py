"""D-41: derivazione dell'anno associativo da una data e dalla data più
antica di un insieme di righe."""

import datetime

from apps.note_spese.anno_associativo import anno_associativo_per_data, calcola_anno_spesa


class TestAnnoAssociativoPerData:
    def test_ottobre_appartiene_al_nuovo_anno(self) -> None:
        assert anno_associativo_per_data(datetime.date(2026, 10, 1)) == 2027

    def test_settembre_appartiene_al_vecchio_anno(self) -> None:
        assert anno_associativo_per_data(datetime.date(2027, 9, 30)) == 2027

    def test_gennaio(self) -> None:
        assert anno_associativo_per_data(datetime.date(2027, 1, 15)) == 2027


class TestCalcolaAnnoSpesa:
    def test_nessuna_riga(self) -> None:
        assert calcola_anno_spesa([]) is None

    def test_usa_la_data_piu_antica(self) -> None:
        date_righe = [datetime.date(2027, 8, 1), datetime.date(2026, 10, 5)]
        assert calcola_anno_spesa(date_righe) == 2027

    def test_riga_singola(self) -> None:
        assert calcola_anno_spesa([datetime.date(2027, 3, 1)]) == 2027
