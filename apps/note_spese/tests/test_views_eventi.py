"""F6f: viste di validazione/modifica/fusione degli eventi (D-49)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import Evento, NotaSpese
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
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


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


class TestEventoListaView:
    def test_capo_qualsiasi_non_accede(self, client, capo_utente) -> None:
        client.force_login(capo_utente)
        response = client.get("/note-spese/eventi/")
        assert response.status_code == 403

    def test_segreteria_vede_lelenco(self, client, segreteria, origine) -> None:
        client.force_login(segreteria)
        response = client.get("/note-spese/eventi/")
        assert response.status_code == 200
        assert origine in response.context["eventi"]


class TestEventoValidaView:
    def test_segreteria_valida(self, client, segreteria, origine) -> None:
        client.force_login(segreteria)
        response = client.post(f"/note-spese/eventi/{origine.pk}/valida/")
        assert response.status_code == 302
        origine.refresh_from_db()
        assert origine.validato is True

    def test_capo_qualsiasi_non_puo_validare(self, client, capo_utente, origine) -> None:
        client.force_login(capo_utente)
        response = client.post(f"/note-spese/eventi/{origine.pk}/valida/")
        assert response.status_code == 403
        origine.refresh_from_db()
        assert origine.validato is False


class TestEventoModificaView:
    def test_segreteria_corregge_nome(self, client, segreteria, origine) -> None:
        client.force_login(segreteria)
        response = client.post(
            f"/note-spese/eventi/{origine.pk}/modifica/",
            {
                "nome": "Campo estivo corretto",
                "data_inizio": "2027-07-01",
                "data_fine": "",
            },
        )
        assert response.status_code == 302
        origine.refresh_from_db()
        assert origine.nome == "Campo estivo corretto"


class TestEventoFondiView:
    def test_segreteria_fonde_due_eventi(
        self, client, segreteria, gruppo, capo, origine, destinazione
    ) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=origine, incarico_altro="Cuoco"
        )
        client.force_login(segreteria)
        response = client.post(
            f"/note-spese/eventi/{origine.pk}/fondi/",
            {"destinazione": destinazione.pk},
        )
        assert response.status_code == 302
        nota.refresh_from_db()
        assert nota.evento_id == destinazione.pk
        assert not Evento.objects.filter(pk=origine.pk).exists()

    def test_destinazione_esclude_lorigine_dalle_opzioni(
        self, client, segreteria, origine, destinazione
    ) -> None:
        client.force_login(segreteria)
        response = client.get(f"/note-spese/eventi/{origine.pk}/fondi/")
        assert response.status_code == 200
        queryset = response.context["form"].fields["destinazione"].queryset
        assert origine not in queryset
        assert destinazione in queryset

    def test_capo_qualsiasi_non_puo_fondere(
        self, client, capo_utente, origine, destinazione
    ) -> None:
        client.force_login(capo_utente)
        response = client.post(
            f"/note-spese/eventi/{origine.pk}/fondi/",
            {"destinazione": destinazione.pk},
        )
        assert response.status_code == 403
        assert Evento.objects.filter(pk=origine.pk).exists()
