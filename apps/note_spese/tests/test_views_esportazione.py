"""F8/D-68: vista di esportazione."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese, RigaSpesa, StatoNota
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


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


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
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test esportazione")


@pytest.fixture
def nota_liquidata(gruppo, capo, evento, categoria) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        stato=StatoNota.LIQUIDATA,
        anno_contabilizzazione=2027,
        numero="2027/0001",
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


class TestNotaEsportaView:
    def test_capo_qualsiasi_non_accede(self, client, capo_utente) -> None:
        client.force_login(capo_utente)
        response = client.get("/note-spese/esporta/")
        assert response.status_code == 403

    def test_segreteria_accede(self, client, segreteria) -> None:
        client.force_login(segreteria)
        response = client.get("/note-spese/esporta/")
        assert response.status_code == 200

    def test_esporta_csv(self, client, segreteria, nota_liquidata) -> None:
        client.force_login(segreteria)
        response = client.post(
            "/note-spese/esporta/",
            {"anno_liquidazione": 2027, "raggruppamento": "EVENTO", "formato": "csv"},
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        contenuto = response.content.decode("utf-8")
        assert "Campo estivo 2027" in contenuto

    def test_esporta_xlsx(self, client, segreteria, nota_liquidata) -> None:
        client.force_login(segreteria)
        response = client.post(
            "/note-spese/esporta/",
            {"anno_liquidazione": 2027, "raggruppamento": "CAPO", "formato": "xlsx"},
        )
        assert response.status_code == 200
        assert response["Content-Type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response["Content-Disposition"].endswith('.xlsx"')
