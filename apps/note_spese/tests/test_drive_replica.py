"""Replica su Drive (D-59, F9): apps/note_spese/drive_replica.py. Ogni
chiamata reale a Drive è mockata su apps.note_spese.drive.carica_file —
questi test verificano solo la logica di accodamento/riconciliazione, non
il protocollo HTTP (già coperto da test_drive.py)."""

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.anagrafica.models import Capo
from apps.note_spese.drive_replica import enqueue_copie_drive, riconcilia_copie_drive
from apps.note_spese.models import (
    Allegato,
    CategoriaSpesa,
    CopiaDrive,
    Evento,
    NotaSpese,
    RigaSpesa,
    StatoCopiaDrive,
    StatoNota,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="1A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test drive", richiede_allegato=False)


@pytest.fixture
def nota(gruppo, capo, evento, categoria) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        numero="2027/0001",
        stato=StatoNota.LIQUIDATA,
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


@pytest.fixture
def drive_configurato(settings):
    settings.DRIVE_SHARED_DRIVE_ID = "drive-id"
    settings.DRIVE_FOLDER_ID = "folder-id"
    return settings


class TestEnqueueCopieDrive:
    def test_noop_se_replica_non_configurata(self, settings, nota) -> None:
        settings.DRIVE_SHARED_DRIVE_ID = ""
        settings.DRIVE_FOLDER_ID = ""
        enqueue_copie_drive(nota)
        assert CopiaDrive.objects.count() == 0

    def test_crea_copia_per_il_pdf(self, drive_configurato, nota) -> None:
        enqueue_copie_drive(nota)
        copie = CopiaDrive.objects.filter(nota=nota)
        assert copie.count() == 1
        assert copie.get().allegato_id is None
        assert copie.get().stato == StatoCopiaDrive.IN_ATTESA

    def test_crea_copia_per_ogni_allegato_distinto(self, drive_configurato, nota) -> None:
        riga = nota.righe.get()
        allegato = Allegato.objects.create(
            file=SimpleUploadedFile("scontrino.jpg", b"finto-jpeg", content_type="image/jpeg")
        )
        allegato.righe.add(riga)

        enqueue_copie_drive(nota)

        assert CopiaDrive.objects.filter(nota=nota).count() == 2
        assert CopiaDrive.objects.filter(nota=nota, allegato=allegato).exists()

    def test_idempotente(self, drive_configurato, nota) -> None:
        enqueue_copie_drive(nota)
        enqueue_copie_drive(nota)
        assert CopiaDrive.objects.filter(nota=nota).count() == 1


class TestRiconciliaCopieDrive:
    def test_noop_se_replica_non_configurata(self, settings, nota) -> None:
        settings.DRIVE_SHARED_DRIVE_ID = ""
        settings.DRIVE_FOLDER_ID = ""
        CopiaDrive.objects.create(nota=nota, allegato=None)
        assert riconcilia_copie_drive() == 0

    def test_copia_riuscita_aggiorna_stato_e_id(self, drive_configurato, nota) -> None:
        # PDF non generato davvero: drive_replica non deve dipendere da
        # WeasyPrint per essere testato, la generazione è già coperta da
        # test_pdf.py/test_views_pdf.py.
        copia = CopiaDrive.objects.create(nota=nota, allegato=None)

        with (
            patch("apps.note_spese.drive_replica.genera_pdf_nota", return_value=b"%PDF-1.4 finto"),
            patch(
                "apps.note_spese.drive_replica.carica_file", return_value="drive-file-id"
            ) as mock_carica,
        ):
            riuscite = riconcilia_copie_drive()

        mock_carica.assert_called_once()
        copia.refresh_from_db()
        assert riuscite == 1
        assert copia.stato == StatoCopiaDrive.COPIATO
        assert copia.drive_file_id == "drive-file-id"
        assert copia.ultimo_errore == ""

    def test_copia_fallita_incrementa_tentativi_e_traccia_errore(
        self, drive_configurato, nota
    ) -> None:
        copia = CopiaDrive.objects.create(nota=nota, allegato=None)

        with (
            patch("apps.note_spese.drive_replica.genera_pdf_nota", return_value=b"%PDF-1.4 finto"),
            patch(
                "apps.note_spese.drive_replica.carica_file", side_effect=RuntimeError("Drive down")
            ),
        ):
            riuscite = riconcilia_copie_drive()

        copia.refresh_from_db()
        assert riuscite == 0
        assert copia.stato == StatoCopiaDrive.FALLITO
        assert copia.tentativi == 1
        assert "Drive down" in copia.ultimo_errore

    def test_copia_gia_riuscita_non_viene_ritentata(self, drive_configurato, nota) -> None:
        CopiaDrive.objects.create(
            nota=nota, allegato=None, stato=StatoCopiaDrive.COPIATO, drive_file_id="già-fatto"
        )

        with patch("apps.note_spese.drive_replica.carica_file") as mock_carica:
            riconcilia_copie_drive()

        mock_carica.assert_not_called()

    def test_oltre_il_massimo_tentativi_non_viene_ritentata(self, drive_configurato, nota) -> None:
        CopiaDrive.objects.create(
            nota=nota, allegato=None, stato=StatoCopiaDrive.FALLITO, tentativi=5
        )

        with patch("apps.note_spese.drive_replica.carica_file") as mock_carica:
            riconcilia_copie_drive()

        mock_carica.assert_not_called()

    def test_allegato_copiato_con_contenuto_corretto(self, drive_configurato, nota) -> None:
        riga = nota.righe.get()
        allegato = Allegato.objects.create(
            file=SimpleUploadedFile("scontrino.jpg", b"finto-jpeg", content_type="image/jpeg")
        )
        allegato.righe.add(riga)
        copia = CopiaDrive.objects.create(nota=nota, allegato=allegato)

        with patch(
            "apps.note_spese.drive_replica.carica_file", return_value="drive-file-id"
        ) as mock_carica:
            riconcilia_copie_drive()

        _, kwargs = mock_carica.call_args
        assert kwargs["contenuto"] == b"finto-jpeg"
        assert kwargs["content_type"] == "image/jpeg"
        copia.refresh_from_db()
        assert copia.stato == StatoCopiaDrive.COPIATO
