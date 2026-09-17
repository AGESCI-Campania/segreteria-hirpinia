"""F6b: viste di sola lettura (elenco, dettaglio, download allegati)."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import Allegato, CategoriaSpesa, Evento, NotaSpese, RigaSpesa
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
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def capo() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def altro_capo() -> Capo:
    return Capo.objects.create(codice_socio="999999Z", nome="Luigi", cognome="Bianchi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def altro_capo_utente(altro_capo: Capo) -> Utente:
    return _persona("altro@example.it", codice_socio=altro_capo.pk)


@pytest.fixture
def utente_senza_capo() -> Utente:
    return _persona("account.gruppo@example.it")


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test viste")


@pytest.fixture
def nota(gruppo, capo, evento, categoria) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


class TestNotaListaView:
    def test_richiede_login(self, client) -> None:
        response = client.get("/note-spese/")
        assert response.status_code == 302

    def test_capo_vede_solo_le_proprie(self, client, capo_utente, nota) -> None:
        client.force_login(capo_utente)
        response = client.get("/note-spese/")
        assert response.status_code == 200
        assert list(response.context["note"]) == [nota]

    def test_altro_capo_non_vede_nota_altrui(self, client, altro_capo_utente, nota) -> None:
        client.force_login(altro_capo_utente)
        response = client.get("/note-spese/")
        assert response.status_code == 200
        assert list(response.context["note"]) == []

    def test_segreteria_vede_tutte(self, client, segreteria, nota) -> None:
        client.force_login(segreteria)
        response = client.get("/note-spese/")
        assert response.status_code == 200
        assert list(response.context["note"]) == [nota]

    def test_account_senza_capo_vede_elenco_vuoto(self, client, utente_senza_capo, nota) -> None:
        client.force_login(utente_senza_capo)
        response = client.get("/note-spese/")
        assert response.status_code == 200
        assert list(response.context["note"]) == []


class TestNotaDettaglioView:
    def test_beneficiario_vede_la_propria_nota(self, client, capo_utente, nota) -> None:
        client.force_login(capo_utente)
        response = client.get(f"/note-spese/{nota.pk}/")
        assert response.status_code == 200
        assert response.context["nota"] == nota

    def test_altro_capo_riceve_404(self, client, altro_capo_utente, nota) -> None:
        client.force_login(altro_capo_utente)
        response = client.get(f"/note-spese/{nota.pk}/")
        assert response.status_code == 404

    def test_segreteria_vede_qualsiasi_nota(self, client, segreteria, nota) -> None:
        client.force_login(segreteria)
        response = client.get(f"/note-spese/{nota.pk}/")
        assert response.status_code == 200

    def test_iban_e_sempre_mascherato(self, client, segreteria, nota) -> None:
        NotaSpese.objects.filter(pk=nota.pk).update(iban="IT60X0542811101000000123456")
        client.force_login(segreteria)
        response = client.get(f"/note-spese/{nota.pk}/")
        contenuto = response.content.decode()
        assert "IT60X0542811101000000123456" not in contenuto
        assert "3456" in contenuto


class TestAllegatoScaricaView:
    @pytest.fixture
    def allegato(self, nota) -> Allegato:
        riga = nota.righe.get()
        allegato = Allegato.objects.create(
            file=SimpleUploadedFile("giustificativo.pdf", b"%PDF-1.4\n%%EOF")
        )
        allegato.righe.add(riga)
        return allegato

    def test_beneficiario_scarica_il_proprio_allegato(self, client, capo_utente, allegato) -> None:
        client.force_login(capo_utente)
        response = client.get(f"/note-spese/allegati/{allegato.pk}/scarica/")
        assert response.status_code == 200

    def test_altro_capo_non_puo_scaricare(self, client, altro_capo_utente, allegato) -> None:
        client.force_login(altro_capo_utente)
        response = client.get(f"/note-spese/allegati/{allegato.pk}/scarica/")
        assert response.status_code == 403

    def test_segreteria_puo_scaricare_qualsiasi_allegato(
        self, client, segreteria, allegato
    ) -> None:
        client.force_login(segreteria)
        response = client.get(f"/note-spese/allegati/{allegato.pk}/scarica/")
        assert response.status_code == 200
