"""F6d: viste di transizione FSM (invio, presa in carico, rilievi, approvazione,
autorizzazione RdZ, liquidazione, respingimento, annullamento)."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import (
    AutorizzazioneRdzConfig,
    CategoriaSpesa,
    Evento,
    ImpostazioniNoteSpese,
    NotaSpese,
    RigaSpesa,
    StatoNota,
)
from apps.note_spese.transizioni import invia_nota, prendi_in_carico
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
def capo_utente(capo: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo.pk)


@pytest.fixture
def altro_capo() -> Capo:
    return Capo.objects.create(codice_socio="999999Z", nome="Luigi", cognome="Bianchi")


@pytest.fixture
def altro_capo_utente(altro_capo: Capo) -> Utente:
    return _persona("altro@example.it", codice_socio=altro_capo.pk)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def rdz(settings) -> Utente:
    utente = _persona(settings.NOTA_SPESE_RDZ_EMAIL_MASCHILE)
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
    return _con_mfa_configurata(utente)


@pytest.fixture
def categoria_senza_allegato() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test transizioni", richiede_allegato=False)


@pytest.fixture
def categoria_con_allegato() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(
        nome="Documentale test transizioni", richiede_allegato=True
    )


@pytest.fixture
def nota_bozza(gruppo, capo, evento, categoria_senza_allegato) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )
    RigaSpesa.objects.create(
        nota=nota,
        categoria=categoria_senza_allegato,
        data=datetime.date(2027, 7, 2),
        importo=Decimal("10"),
    )
    return nota


def _url(nome: str, pk: int) -> str:
    return f"/note-spese/{pk}/{nome}/"


def _porta_in_verifica(nota: NotaSpese, capo_utente: Utente, segreteria: Utente) -> NotaSpese:
    """`stato` è un `FSMField(protected=True)` (stessa trappola già nota da
    M4): non assegnabile direttamente, si avanza solo chiamando le vere
    transizioni di `transizioni.py`."""
    nota = invia_nota(nota, capo_utente)
    return prendi_in_carico(nota, segreteria)


class TestNotaInviaView:
    def test_beneficiario_invia_la_propria_nota(self, client, capo_utente, nota_bozza) -> None:
        client.force_login(capo_utente)
        response = client.post(_url("invia", nota_bozza.pk))
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.INVIATA
        assert nota_bozza.numero

    def test_altro_capo_non_vede_nemmeno_la_nota(
        self, client, altro_capo_utente, nota_bozza
    ) -> None:
        """Fuori dal perimetro di `note_visibili()` (D-66): 404, non un
        messaggio di permesso — stesso comportamento del dettaglio (F6b)."""
        client.force_login(altro_capo_utente)
        response = client.post(_url("invia", nota_bozza.pk))
        assert response.status_code == 404
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.BOZZA

    def test_segreteria_non_puo_inviare_al_posto_del_capo(
        self, client, segreteria, nota_bozza
    ) -> None:
        """Segreteria vede la nota (D-66) ma non è il beneficiario né il
        compilatore per conto terzi (D-36): il servizio respinge, la view
        mostra il motivo senza il codice di decisione interno."""
        client.force_login(segreteria)
        response = client.post(_url("invia", nota_bozza.pk), follow=True)
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.BOZZA
        messaggi = [str(m) for m in response.context["messages"]]
        assert any("Solo il beneficiario" in m for m in messaggi)
        assert not any("D-36" in m for m in messaggi)

    def test_richiede_login(self, client, nota_bozza) -> None:
        response = client.post(_url("invia", nota_bozza.pk))
        assert response.status_code == 302
        assert "/accounts/" in response.url or "login" in response.url


class TestFlussoCompleto:
    """Percorso BOZZA -> INVIATA -> IN_VERIFICA -> APPROVATA -> AUTORIZZATA_RDZ
    -> LIQUIDATA, con configurazione RdZ SINGOLA."""

    @pytest.fixture(autouse=True)
    def _config_singola(self) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.SINGOLA}
        )

    def test_percorso_fino_alla_liquidazione(
        self, client, capo_utente, segreteria, rdz, nota_bozza
    ) -> None:
        client.force_login(capo_utente)
        client.post(_url("invia", nota_bozza.pk))
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.INVIATA

        client.force_login(segreteria)
        client.post(_url("prendi-in-carico", nota_bozza.pk))
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.IN_VERIFICA

        client.post(_url("approva", nota_bozza.pk))
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.APPROVATA

        client.force_login(rdz)
        client.post(_url("autorizza-rdz", nota_bozza.pk))
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.AUTORIZZATA_RDZ

        client.force_login(segreteria)
        response = client.post(
            _url("liquida", nota_bozza.pk),
            {
                "anno_liquidazione": 2027,
                "modalita_pagamento": "CONTANTI",
                "data_pagamento": "2027-10-01",
            },
        )
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.LIQUIDATA
        assert nota_bozza.anno_contabilizzazione == 2027
        assert nota_bozza.modalita_pagamento == "CONTANTI"
        assert nota_bozza.data_pagamento == datetime.date(2027, 10, 1)

    def test_liquida_bonifico_senza_riferimento_e_bloccante(
        self, client, capo_utente, segreteria, rdz, nota_bozza
    ) -> None:
        client.force_login(capo_utente)
        client.post(_url("invia", nota_bozza.pk))
        client.force_login(segreteria)
        client.post(_url("prendi-in-carico", nota_bozza.pk))
        client.post(_url("approva", nota_bozza.pk))
        client.force_login(rdz)
        client.post(_url("autorizza-rdz", nota_bozza.pk))

        client.force_login(segreteria)
        response = client.post(
            _url("liquida", nota_bozza.pk),
            {
                "anno_liquidazione": 2027,
                "modalita_pagamento": "BONIFICO",
                "data_pagamento": "2027-10-01",
            },
        )
        assert response.status_code == 200
        assert "riferimento_tracciabilita" in response.context["form"].errors
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.AUTORIZZATA_RDZ

    def test_capo_non_puo_approvare(self, client, capo_utente, segreteria, nota_bozza) -> None:
        client.force_login(capo_utente)
        client.post(_url("invia", nota_bozza.pk))
        client.force_login(segreteria)
        client.post(_url("prendi-in-carico", nota_bozza.pk))

        client.force_login(capo_utente)
        response = client.post(_url("approva", nota_bozza.pk), follow=True)
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.IN_VERIFICA
        messaggi = [str(m) for m in response.context["messages"]]
        assert messaggi


class TestNotaRespingiView:
    def test_respingimento_richiede_causale(
        self, client, segreteria, capo_utente, nota_bozza
    ) -> None:
        _porta_in_verifica(nota_bozza, capo_utente, segreteria)
        client.force_login(segreteria)
        response = client.post(_url("respingi", nota_bozza.pk), {"causale": ""})
        assert response.status_code == 200
        assert response.context["form"].errors
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.IN_VERIFICA

    def test_respingimento_con_causale(self, client, segreteria, capo_utente, nota_bozza) -> None:
        _porta_in_verifica(nota_bozza, capo_utente, segreteria)
        client.force_login(segreteria)
        response = client.post(
            _url("respingi", nota_bozza.pk), {"causale": "Documentazione insufficiente"}
        )
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.RESPINTA
        assert nota_bozza.causale_respinta == "Documentazione insufficiente"


class TestRilievi:
    def test_richiedi_integrazione_si_sblocca_solo_con_nuovo_allegato(
        self, client, segreteria, capo_utente, nota_bozza
    ) -> None:
        _porta_in_verifica(nota_bozza, capo_utente, segreteria)
        riga = nota_bozza.righe.get()

        client.force_login(segreteria)
        response = client.post(
            _url("richiedi-integrazione", nota_bozza.pk),
            {"riga": riga.pk, "testo": "Manca lo scontrino"},
        )
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.DA_INTEGRARE

        # Senza un nuovo allegato la conferma resta bloccata (D-38).
        client.force_login(capo_utente)
        response = client.post(_url("conferma-integrazione", nota_bozza.pk), follow=True)
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.DA_INTEGRARE

        riga.allegati.create(file=SimpleUploadedFile("scontrino.pdf", b"%PDF-1.4\n%%EOF"))
        response = client.post(_url("conferma-integrazione", nota_bozza.pk))
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.IN_VERIFICA

    def test_richiedi_conferma_si_sblocca_con_assenso(
        self, client, segreteria, capo_utente, nota_bozza
    ) -> None:
        _porta_in_verifica(nota_bozza, capo_utente, segreteria)
        riga = nota_bozza.righe.get()

        client.force_login(segreteria)
        client.post(
            _url("richiedi-conferma", nota_bozza.pk),
            {"riga": riga.pk, "testo": "Importo corretto a 8 euro"},
        )
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.DA_CONFERMARE

        client.force_login(capo_utente)
        response = client.post(_url("conferma-correzione", nota_bozza.pk))
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.IN_VERIFICA


class TestNotaAnnullaView:
    def test_beneficiario_annulla_una_bozza(self, client, capo_utente, nota_bozza) -> None:
        client.force_login(capo_utente)
        response = client.post(_url("annulla", nota_bozza.pk))
        assert response.status_code == 302
        nota_bozza.refresh_from_db()
        assert nota_bozza.stato == StatoNota.ANNULLATA
