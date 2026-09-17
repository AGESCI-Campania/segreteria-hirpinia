"""D-49: fusione degli eventi."""

import datetime

import pytest
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.eventi import fondi_eventi
from apps.note_spese.models import Evento, NotaSpese
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, codice_socio: str | None = None) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, codice_socio=codice_socio
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def origine() -> Evento:
    return Evento.objects.create(
        nome="Campo estivo", data_inizio=datetime.date(2027, 7, 1), validato=False
    )


@pytest.fixture
def destinazione() -> Evento:
    return Evento.objects.create(
        nome="Campo Estivo 2027", data_inizio=datetime.date(2027, 7, 1), validato=True
    )


class TestFondiEventi:
    def test_sposta_le_note_e_cancella_origine(
        self, gruppo, capo, origine, destinazione, segreteria
    ) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=origine, incarico_altro="Cuoco"
        )

        interessate = fondi_eventi(origine, destinazione, segreteria)

        nota.refresh_from_db()
        assert nota.evento_id == destinazione.pk
        assert interessate == [nota]
        assert not Evento.objects.filter(pk=origine.pk).exists()

    def test_traccia_in_auditlog_origine_e_destinazione(
        self, gruppo, capo, origine, destinazione, segreteria
    ) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=origine, incarico_altro="Cuoco"
        )
        pk_origine, pk_destinazione = origine.pk, destinazione.pk

        fondi_eventi(origine, destinazione, segreteria)

        ct = ContentType.objects.get_for_model(NotaSpese)
        log = (
            LogEntry.objects.filter(content_type=ct, object_id=str(nota.pk)).order_by("-id").first()
        )
        assert log.changes["evento"] == [str(pk_origine), str(pk_destinazione)]

    def test_capo_non_puo_fondere(self, gruppo, capo, origine, destinazione, capo_utente) -> None:
        with pytest.raises(PermissionDenied):
            fondi_eventi(origine, destinazione, capo_utente)
        assert Evento.objects.filter(pk=origine.pk).exists()

    def test_non_si_puo_fondere_un_evento_con_se_stesso(self, origine, segreteria) -> None:
        with pytest.raises(ValidationError):
            fondi_eventi(origine, origine, segreteria)

    def test_nessuna_nota_da_spostare(self, origine, destinazione, segreteria) -> None:
        interessate = fondi_eventi(origine, destinazione, segreteria)
        assert interessate == []
        assert not Evento.objects.filter(pk=origine.pk).exists()
