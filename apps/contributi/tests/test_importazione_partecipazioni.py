"""Caricamento massivo delle partecipazioni da xlsx/CSV (D-21)."""

import datetime
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.contributi.importazione_partecipazioni import (
    SOSPETTA,
    applica_piano_partecipazioni,
    costruisci_piano_partecipazioni,
)
from apps.contributi.models import (
    Campagna,
    ImportazionePartecipazioni,
    Partecipazione,
    TipologiaCampo,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str) -> Utente:
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
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


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    u = _persona("cg-avellino1@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return u


@pytest.fixture
def segreteria() -> Utente:
    u = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
    return u


def _riga(
    *, codice_socio="10001", cognome="ROSSI", nome="MARIO", codice_tipologia="CFM", **override
):
    riga = {
        "codice_socio": codice_socio,
        "cognome": cognome,
        "nome": nome,
        "codice_tipologia": codice_tipologia,
        "data_inizio": "01/06/2026",
        "data_fine": "08/06/2026",
        "luogo": "Base scout",
        "quota_versata": "",
    }
    riga.update(override)
    return riga


class TestCostruisciPiano:
    def test_riga_valida(self, capo, campagna, tipologia, cg_gruppo):
        piano = costruisci_piano_partecipazioni([_riga()], campagna=campagna, utente=cg_gruppo)
        assert len(piano.valide) == 1
        assert piano.valide[0].quota_versata == Decimal("51.50")

    def test_riga_fuori_perimetro_per_account_di_gruppo(
        self, capo, campagna, tipologia, altro_gruppo
    ):
        cg_altro = _persona("cg-altro@campania.agesci.it")
        Ruolo.objects.create(utente=cg_altro, tipo=Ruolo.Tipo.CG, gruppo=altro_gruppo)

        piano = costruisci_piano_partecipazioni([_riga()], campagna=campagna, utente=cg_altro)

        assert piano.valide == []
        assert any(a.campo == "Perimetro" for a in piano.anomalie)

    def test_riga_sospetta_mismatch_nome_cognome(self, capo, campagna, tipologia, cg_gruppo):
        piano = costruisci_piano_partecipazioni(
            [_riga(nome="LUIGI")], campagna=campagna, utente=cg_gruppo
        )
        assert piano.valide == []
        assert any(a.livello == SOSPETTA for a in piano.anomalie)

    def test_riga_duplicata_esatta_no_op(self, capo, campagna, tipologia, cg_gruppo):
        Partecipazione.objects.create(
            campagna=campagna,
            capo=capo,
            gruppo=capo.censimenti.get(anno_scout=ANNO).gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base scout",
            quota_versata=Decimal("51.50"),
        )

        piano = costruisci_piano_partecipazioni([_riga()], campagna=campagna, utente=cg_gruppo)

        assert piano.valide == []
        assert piano.conflitti == []
        assert piano.gia_presenti == [(2, "10001")]

    def test_riga_stessa_chiave_campi_diversi_e_conflitto(
        self, capo, campagna, tipologia, cg_gruppo
    ):
        esistente = Partecipazione.objects.create(
            campagna=campagna,
            capo=capo,
            gruppo=capo.censimenti.get(anno_scout=ANNO).gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base scout",
            quota_versata=Decimal("51.50"),
        )

        piano = costruisci_piano_partecipazioni(
            [_riga(luogo="Altra base")], campagna=campagna, utente=cg_gruppo
        )

        assert piano.valide == []
        assert len(piano.conflitti) == 1
        assert piano.conflitti[0].esistente == esistente
        assert "luogo" in piano.conflitti[0].differenze

        esistente.refresh_from_db()
        assert esistente.luogo == "Base scout"  # non toccato

    def test_quota_versata_vuota_precompilata(self, capo, campagna, tipologia, cg_gruppo):
        piano = costruisci_piano_partecipazioni(
            [_riga(quota_versata="")], campagna=campagna, utente=cg_gruppo
        )
        assert piano.valide[0].quota_versata == tipologia.quota_default

    def test_quota_versata_esplicita_rispettata(self, capo, campagna, tipologia, cg_gruppo):
        piano = costruisci_piano_partecipazioni(
            [_riga(quota_versata="30,00")], campagna=campagna, utente=cg_gruppo
        )
        assert piano.valide[0].quota_versata == Decimal("30.00")

    def test_campagna_non_aperta_non_valida(self, capo, campagna, tipologia, cg_gruppo):
        Campagna.objects.filter(pk=campagna.pk).update(stato="IN_VALUTAZIONE")
        campagna_aggiornata = Campagna.objects.get(pk=campagna.pk)

        piano = costruisci_piano_partecipazioni(
            [_riga()], campagna=campagna_aggiornata, utente=cg_gruppo
        )

        assert piano.valido is False

    def test_campagna_fuori_finestra_non_valida(self, capo, tipologia, cg_gruppo):
        campagna_passata = Campagna.objects.create(
            anno=2020,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2019, 10, 1),
            data_fine_inserimento=datetime.date(2019, 12, 31),
        )
        piano = costruisci_piano_partecipazioni(
            [_riga()], campagna=campagna_passata, utente=cg_gruppo
        )
        assert piano.valido is False

    def test_capo_censito_in_e9001_bloccato_per_segreteria(self, campagna, tipologia, segreteria):
        e9001 = Gruppo.objects.get(codice="E9001")
        capo_e9001 = Capo.objects.create(codice_socio="20002", nome="LUCA", cognome="BIANCHI")
        CensimentoCapo.objects.create(capo=capo_e9001, anno_scout=ANNO, gruppo=e9001)

        piano = costruisci_piano_partecipazioni(
            [_riga(codice_socio="20002", cognome="BIANCHI", nome="LUCA")],
            campagna=campagna,
            utente=segreteria,
        )

        assert piano.valide == []
        assert any(a.campo == "Perimetro" for a in piano.anomalie)


class TestApplicaPiano:
    def test_applica_scrive_solo_valide(self, capo, campagna, tipologia, cg_gruppo):
        piano = costruisci_piano_partecipazioni([_riga()], campagna=campagna, utente=cg_gruppo)
        file_originale = ContentFile(b"contenuto", name="partecipazioni.xlsx")

        importazione = applica_piano_partecipazioni(
            piano, file_originale=file_originale, utente=cg_gruppo
        )

        assert Partecipazione.objects.filter(campagna=campagna, capo=capo).count() == 1
        assert importazione.conteggi["partecipazioni_create"] == 1
        assert ImportazionePartecipazioni.objects.count() == 1

    def test_conflitti_non_scritti(self, capo, campagna, tipologia, cg_gruppo):
        Partecipazione.objects.create(
            campagna=campagna,
            capo=capo,
            gruppo=capo.censimenti.get(anno_scout=ANNO).gruppo,
            tipologia=tipologia,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base scout",
            quota_versata=Decimal("51.50"),
        )
        piano = costruisci_piano_partecipazioni(
            [_riga(luogo="Altra base")], campagna=campagna, utente=cg_gruppo
        )
        file_originale = ContentFile(b"contenuto", name="partecipazioni.xlsx")

        applica_piano_partecipazioni(piano, file_originale=file_originale, utente=cg_gruppo)

        assert Partecipazione.objects.filter(campagna=campagna, capo=capo).count() == 1

    def test_piano_non_valido_solleva_errore(self, capo, tipologia, cg_gruppo):
        campagna_passata = Campagna.objects.create(
            anno=2020,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2019, 10, 1),
            data_fine_inserimento=datetime.date(2019, 12, 31),
        )
        piano = costruisci_piano_partecipazioni(
            [_riga()], campagna=campagna_passata, utente=cg_gruppo
        )
        with pytest.raises(ValueError):
            applica_piano_partecipazioni(
                piano, file_originale=ContentFile(b"x", name="p.xlsx"), utente=cg_gruppo
            )


class TestFormatoCSV:
    def test_csv_stesso_risultato_dello_xlsx(self, capo, campagna, tipologia, cg_gruppo):
        from apps.contributi.importazione_partecipazioni import leggi_righe_csv

        testo_csv = (
            "codice_socio,cognome,nome,codice_tipologia,data_inizio,data_fine,luogo,quota_versata\n"
            "10001,ROSSI,MARIO,CFM,01/06/2026,08/06/2026,Base scout,\n"
        )
        righe = leggi_righe_csv(testo_csv)
        piano = costruisci_piano_partecipazioni(righe, campagna=campagna, utente=cg_gruppo)

        assert len(piano.valide) == 1
        assert piano.valide[0].quota_versata == Decimal("51.50")
