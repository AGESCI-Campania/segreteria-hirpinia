"""F7/D-62: notifiche puntuali al beneficiario sugli eventi di stato."""

import datetime
from decimal import Decimal

import pytest
from django.core import mail

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import (
    CategoriaSpesa,
    Evento,
    ModalitaPagamento,
    NotaSpese,
    RigaSpesa,
)
from apps.note_spese.transizioni import (
    approva,
    invia_nota,
    liquida,
    prendi_in_carico,
    respingi,
    richiedi_conferma,
    richiedi_integrazione,
)
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
    return Capo.objects.create(
        codice_socio="123456A", nome="Mario", cognome="Rossi", email="mario.rossi@example.it"
    )


@pytest.fixture
def capo_senza_email() -> Capo:
    return Capo.objects.create(codice_socio="999999Z", nome="Luigi", cognome="Bianchi")


@pytest.fixture
def capo_utente(capo: Capo) -> Utente:
    return _persona("account.mario@example.it", codice_socio=capo.pk)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test notifiche", richiede_allegato=False)


def _nota_con_riga(gruppo, capo, evento, categoria) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("20.00")
    )
    return nota


class TestNotificaApprovazione:
    def test_email_al_beneficiario(
        self, gruppo, capo, evento, categoria, capo_utente, segreteria
    ) -> None:
        nota = _nota_con_riga(gruppo, capo, evento, categoria)
        nota = invia_nota(nota, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        mail.outbox.clear()

        approva(nota, segreteria)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [capo.email]
        assert str(nota.numero) in mail.outbox[0].body

    def test_nessun_invio_senza_email_censita(
        self, gruppo, capo_senza_email, evento, categoria, segreteria
    ) -> None:
        nota = _nota_con_riga(gruppo, capo_senza_email, evento, categoria)
        utente_senza_email = _persona("account.luigi@example.it", codice_socio=capo_senza_email.pk)
        nota = invia_nota(nota, utente_senza_email)
        nota = prendi_in_carico(nota, segreteria)
        mail.outbox.clear()

        approva(nota, segreteria)

        assert mail.outbox == []


class TestNotificaRespingimento:
    def test_email_con_causale(
        self, gruppo, capo, evento, categoria, capo_utente, segreteria
    ) -> None:
        nota = _nota_con_riga(gruppo, capo, evento, categoria)
        nota = invia_nota(nota, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        mail.outbox.clear()

        respingi(nota, segreteria, "Documentazione insufficiente")

        assert len(mail.outbox) == 1
        assert "Documentazione insufficiente" in mail.outbox[0].body


class TestNotificaRilievo:
    def test_richiedi_integrazione_invia_email_con_motivo(
        self, gruppo, capo, evento, categoria, capo_utente, segreteria
    ) -> None:
        nota = _nota_con_riga(gruppo, capo, evento, categoria)
        nota = invia_nota(nota, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        riga = nota.righe.get()
        mail.outbox.clear()

        richiedi_integrazione(nota, segreteria, riga, "Manca lo scontrino")

        assert len(mail.outbox) == 1
        assert "Manca lo scontrino" in mail.outbox[0].body

    def test_richiedi_conferma_invia_email_con_motivo(
        self, gruppo, capo, evento, categoria, capo_utente, segreteria
    ) -> None:
        nota = _nota_con_riga(gruppo, capo, evento, categoria)
        nota = invia_nota(nota, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        riga = nota.righe.get()
        mail.outbox.clear()

        richiedi_conferma(nota, segreteria, riga, "Importo corretto a 15 euro")

        assert len(mail.outbox) == 1
        assert "Importo corretto a 15 euro" in mail.outbox[0].body


class TestNotificaLiquidazione:
    def test_email_alla_liquidazione(
        self, gruppo, capo, evento, categoria, capo_utente, segreteria
    ) -> None:
        nota = _nota_con_riga(gruppo, capo, evento, categoria)
        nota = invia_nota(nota, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        mail.outbox.clear()

        liquida(
            nota,
            segreteria,
            anno_liquidazione=2027,
            modalita_pagamento=ModalitaPagamento.CONTANTI,
            data_pagamento=datetime.date(2027, 10, 1),
        )

        assert len(mail.outbox) == 1
        assert str(nota.numero) in mail.outbox[0].body
