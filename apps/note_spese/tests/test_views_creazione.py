"""F6c: viste di creazione nota/evento/riga/allegato."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.note_spese.anno_associativo import anno_associativo_per_data
from apps.note_spese.creazione import crea_nota_bozza
from apps.note_spese.models import CategoriaSpesa, Evento, NotaSpese
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO_CORRENTE = anno_associativo_per_data(timezone.now().date())


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
def capo(gruppo) -> Capo:
    capo = Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")
    CensimentoCapo.objects.create(capo=capo, anno_scout=ANNO_CORRENTE, gruppo=gruppo)
    return capo


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def incarico(capo, gruppo) -> IncaricoUnita:
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=ANNO_CORRENTE,
        gruppo_servizio=gruppo,
        codice_unita="R1",
        branca=BrancaUnita.RS,
        funzione=FunzioneIncarico.CAPO_UNITA,
        origine=OrigineIncarico.MANUALE,
    )


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def categoria_documentale() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test viste")


@pytest.fixture
def nota(capo, capo_utente, evento, incarico) -> NotaSpese:
    return crea_nota_bozza(
        utente=capo_utente, beneficiario=capo, evento=evento, incarico=incarico, incarico_altro=""
    )


class TestNotaCreaView:
    def test_get_richiede_login(self, client) -> None:
        response = client.get("/note-spese/nuova/")
        assert response.status_code == 302

    def test_capo_crea_la_propria_nota(self, client, capo_utente, evento, incarico) -> None:
        client.force_login(capo_utente)
        response = client.post(
            "/note-spese/nuova/",
            {
                "evento": evento.pk,
                "incarico": incarico.pk,
                "incarico_altro": "",
                "iban": "",
                "intestatario_iban": "",
            },
        )
        assert response.status_code == 302
        nota = NotaSpese.objects.get()
        assert nota.beneficiario_id == capo_utente.codice_socio

    def test_capo_qualsiasi_non_vede_campo_beneficiario_terzi(self, client, capo_utente) -> None:
        client.force_login(capo_utente)
        response = client.get("/note-spese/nuova/")
        assert b"beneficiario_codice_socio" not in response.content

    def test_capo_non_puo_forzare_un_beneficiario_diverso(
        self, client, capo_utente, evento, capo
    ) -> None:
        altro_capo = Capo.objects.create(codice_socio="999999Z", nome="Luigi", cognome="Bianchi")
        CensimentoCapo.objects.create(
            capo=altro_capo, anno_scout=ANNO_CORRENTE, gruppo=capo.censimenti.get().gruppo
        )
        client.force_login(capo_utente)
        response = client.post(
            "/note-spese/nuova/",
            {
                "beneficiario_codice_socio": altro_capo.pk,
                "evento": evento.pk,
                "incarico_altro": "Cuoco",
                "iban": "",
                "intestatario_iban": "",
            },
        )
        assert response.status_code == 200
        assert not NotaSpese.objects.exists()

    def test_segreteria_crea_per_conto_terzi(self, client, segreteria, capo, evento) -> None:
        client.force_login(segreteria)
        response = client.post(
            "/note-spese/nuova/",
            {
                "beneficiario_codice_socio": capo.pk,
                "evento": evento.pk,
                "incarico_altro": "Cuoco",
                "iban": "",
                "intestatario_iban": "",
            },
        )
        assert response.status_code == 302
        nota = NotaSpese.objects.get()
        assert nota.beneficiario_id == capo.pk


class TestEventoCreaView:
    def test_capo_crea_un_evento_non_validato(self, client, capo_utente) -> None:
        client.force_login(capo_utente)
        response = client.post(
            "/note-spese/eventi/nuovo/",
            {"nome": "Uscita di reparto", "data_inizio": "2027-05-01", "data_fine": ""},
        )
        assert response.status_code == 302
        evento = Evento.objects.get(nome="Uscita di reparto")
        assert evento.validato is False
        assert evento.creato_da_id == capo_utente.pk


class TestRigaCreaView:
    def test_beneficiario_aggiunge_una_riga_documentale(
        self, client, capo_utente, nota, categoria_documentale
    ) -> None:
        client.force_login(capo_utente)
        response = client.post(
            f"/note-spese/{nota.pk}/righe/aggiungi/",
            {
                "categoria": categoria_documentale.pk,
                "data_spesa": "2027-07-02",
                "descrizione": "Cena di gruppo",
                "tratta_testo": "",
                "importo": "15.50",
            },
        )
        assert response.status_code == 302
        assert nota.righe.count() == 1

    def test_altro_capo_riceve_404(self, client, nota, categoria_documentale) -> None:
        """La nota è fuori dal perimetro di `note_visibili()` per un capo
        estraneo (D-65/D-66): stesso comportamento di `NotaDettaglioView`,
        404 e non 403, per non rivelarne l'esistenza."""
        altro = _persona("altro@example.it", codice_socio="555555X")
        client.force_login(altro)
        response = client.post(
            f"/note-spese/{nota.pk}/righe/aggiungi/",
            {
                "categoria": categoria_documentale.pk,
                "data_spesa": "2027-07-02",
                "descrizione": "",
                "tratta_testo": "",
                "importo": "10",
            },
        )
        assert response.status_code == 404
        assert nota.righe.count() == 0

    def test_segreteria_non_compilatrice_riceve_403(
        self, client, segreteria, nota, categoria_documentale
    ) -> None:
        """La segreteria vede la nota (`note_visibili()` include tutte, D-65)
        ma non è beneficiaria né compilatrice: la nota non passa da lei,
        quindi non può aggiungervi righe — 403, non 404, dato che la nota è
        visibile."""
        client.force_login(segreteria)
        response = client.post(
            f"/note-spese/{nota.pk}/righe/aggiungi/",
            {
                "categoria": categoria_documentale.pk,
                "data_spesa": "2027-07-02",
                "descrizione": "",
                "tratta_testo": "",
                "importo": "10",
            },
        )
        assert response.status_code == 403
        assert nota.righe.count() == 0


class TestAllegatoCaricaView:
    def test_beneficiario_carica_un_allegato_sulla_riga(
        self, client, capo_utente, nota, categoria_documentale
    ) -> None:
        riga = nota.righe.create(
            categoria=categoria_documentale, data=datetime.date(2027, 7, 2), importo="10"
        )
        client.force_login(capo_utente)
        response = client.post(
            f"/note-spese/{nota.pk}/righe/{riga.pk}/allegati/carica/",
            {"file": SimpleUploadedFile("giustificativo.pdf", b"%PDF-1.4\n%%EOF")},
        )
        assert response.status_code == 302
        assert riga.allegati.count() == 1
