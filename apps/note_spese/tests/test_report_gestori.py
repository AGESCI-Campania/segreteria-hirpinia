"""F7/D-64: report periodico ai gestori."""

import datetime
from decimal import Decimal

import pytest
from django.core import mail

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import (
    CategoriaSpesa,
    Evento,
    ImpostazioniNoteSpese,
    NotaSpese,
    RigaSpesa,
    StatoNota,
)
from apps.note_spese.report_gestori import destinatari_report, invia_report_gestori
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
    return Capo.objects.create(codice_socio="1A", nome="Mario", cognome="Rossi")


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test report", richiede_allegato=False)


def _nota(gruppo, capo, evento, categoria, stato, **extra) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
        stato=stato,
        **extra,
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("10")
    )
    return nota


MARTEDI_9_30 = datetime.datetime(2027, 3, 2, 9, 30, tzinfo=datetime.UTC)


def _impostazioni(**campi) -> ImpostazioniNoteSpese:
    impostazioni = ImpostazioniNoteSpese.corrente()
    for campo, valore in campi.items():
        setattr(impostazioni, campo, valore)
    impostazioni.save()
    return impostazioni


class TestDestinatariReport:
    def test_nessuna_categoria_selezionata_nessun_destinatario(self) -> None:
        impostazioni = _impostazioni()
        assert destinatari_report(impostazioni) == []

    def test_segreteria_inclusa_se_selezionata(self) -> None:
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        impostazioni = _impostazioni(report_destinatari_segreteria=True)
        assert destinatari_report(impostazioni) == [seg.email]

    def test_rdz_esclusa_se_non_selezionata(self) -> None:
        rdz = _persona("rdz@campania.agesci.it")
        Ruolo.objects.create(utente=rdz, tipo=Ruolo.Tipo.RDZ)
        impostazioni = _impostazioni(report_destinatari_segreteria=True)
        assert destinatari_report(impostazioni) == []

    def test_utente_senza_email_escluso(self) -> None:
        seg = _persona("")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        impostazioni = _impostazioni(report_destinatari_segreteria=True)
        assert destinatari_report(impostazioni) == []


class TestInviaReportGestori:
    def test_nessun_invio_senza_giorni_configurati(self, gruppo, capo, evento, categoria) -> None:
        _nota(gruppo, capo, evento, categoria, StatoNota.IN_VERIFICA)
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        _impostazioni(report_destinatari_segreteria=True)

        inviate = invia_report_gestori(MARTEDI_9_30)

        assert inviate == 0
        assert mail.outbox == []

    def test_nessun_invio_prima_dellorario(self, gruppo, capo, evento, categoria) -> None:
        _nota(gruppo, capo, evento, categoria, StatoNota.IN_VERIFICA)
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        _impostazioni(
            report_destinatari_segreteria=True,
            report_giorni_settimana=[1],
            report_orario=datetime.time(10, 0),
        )

        inviate = invia_report_gestori(MARTEDI_9_30)

        assert inviate == 0
        assert mail.outbox == []

    def test_nessun_invio_giorno_sbagliato(self, gruppo, capo, evento, categoria) -> None:
        _nota(gruppo, capo, evento, categoria, StatoNota.IN_VERIFICA)
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        _impostazioni(
            report_destinatari_segreteria=True,
            report_giorni_settimana=[0],  # lunedì, ma MARTEDI_9_30 è martedì
            report_orario=datetime.time(9, 0),
        )

        inviate = invia_report_gestori(MARTEDI_9_30)

        assert inviate == 0
        assert mail.outbox == []

    def test_invio_su_giorno_e_orario_corretti(self, gruppo, capo, evento, categoria) -> None:
        _nota(gruppo, capo, evento, categoria, StatoNota.IN_VERIFICA)
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        _impostazioni(
            report_destinatari_segreteria=True,
            report_giorni_settimana=[1],
            report_orario=datetime.time(9, 0),
        )

        inviate = invia_report_gestori(MARTEDI_9_30)

        assert inviate == 1
        assert mail.outbox[0].to == [seg.email]

    def test_liquidata_esclusa_dal_contenuto(self, gruppo, capo, evento, categoria) -> None:
        _nota(gruppo, capo, evento, categoria, StatoNota.LIQUIDATA)
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        _impostazioni(
            report_destinatari_segreteria=True,
            report_giorni_settimana=[1],
            report_orario=datetime.time(9, 0),
        )

        inviate = invia_report_gestori(MARTEDI_9_30)

        assert inviate == 0
        assert mail.outbox == []

    def test_non_reinvia_lo_stesso_giorno(self, gruppo, capo, evento, categoria) -> None:
        _nota(gruppo, capo, evento, categoria, StatoNota.IN_VERIFICA)
        seg = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=seg, tipo=Ruolo.Tipo.SEGRETERIA)
        _impostazioni(
            report_destinatari_segreteria=True,
            report_giorni_settimana=[1],
            report_orario=datetime.time(9, 0),
        )

        prima = invia_report_gestori(MARTEDI_9_30)
        piu_tardi_stesso_giorno = MARTEDI_9_30 + datetime.timedelta(hours=1)
        seconda = invia_report_gestori(piu_tardi_stesso_giorno)

        assert prima == 1
        assert seconda == 0
        assert len(mail.outbox) == 1
