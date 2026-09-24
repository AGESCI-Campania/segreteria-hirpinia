"""F8/D-67: vista di download del PDF. Richiede le librerie native
WeasyPrint (Pango/Cairo): su macOS locale va lanciata con
`DYLD_LIBRARY_PATH=/opt/homebrew/lib` (docs/docker.md), non serve in
Docker/CI — stesso vincolo preesistente di
apps.contributi.tests.test_views_riepilogo.TestCampagnaReportPdfView."""

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese, RigaSpesa
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, codice_socio: str | None = None) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(
        username=f"u{n}",
        email=email,
        tipo=TipoUtente.PERSONA,
        codice_socio=codice_socio,
        stato=StatoUtente.ATTIVO,
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="1A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def altro_capo_utente() -> Utente:
    Capo.objects.create(codice_socio="2B", nome="Luigi", cognome="Bianchi")
    return _persona("altro@example.it", codice_socio="2B")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test pdf view", richiede_allegato=False)


@pytest.fixture
def nota(gruppo, capo, evento, categoria) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


class TestNotaPdfView:
    def test_beneficiario_scarica_il_proprio_pdf(self, client, capo_utente, nota) -> None:
        client.force_login(capo_utente)
        response = client.get(f"/note-spese/{nota.pk}/pdf/")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content[:4] == b"%PDF"

    def test_altro_capo_non_accede(self, client, altro_capo_utente, nota) -> None:
        client.force_login(altro_capo_utente)
        response = client.get(f"/note-spese/{nota.pk}/pdf/")
        assert response.status_code == 404
