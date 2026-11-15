"""Programma dei lavori della seduta (programma.py)."""

import datetime
import io
import zoneinfo

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from pypdf import PdfReader

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.assemblee import odg, programma
from apps.assemblee.models import (
    Assemblea,
    AventeDiritto,
    IncaricoAssemblea,
    OperatoreVoto,
    Provenienza,
    RuoloAssemblea,
    Seduta,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ROMA = zoneinfo.ZoneInfo("Europe/Rome")
GIORNO = datetime.date(2026, 11, 22)


def ore(h: int, m: int = 0) -> datetime.time:
    return datetime.time(h, m)


def alle(h: int, m: int = 0, giorno: datetime.date = GIORNO) -> datetime.datetime:
    return datetime.datetime.combine(giorno, ore(h, m), tzinfo=ROMA)


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def assemblea() -> Assemblea:
    return Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)


@pytest.fixture
def seduta(assemblea) -> Seduta:
    return Seduta.objects.create(assemblea=assemblea, convocazione=1, data=GIORNO, luogo="Avellino")


@pytest.fixture
def presidente(assemblea) -> Utente:
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    avente = AventeDiritto.objects.create(
        assemblea=assemblea,
        nome="Mario",
        cognome="Rossi",
        gruppo=gruppo,
        anno_censimento=2026,
        provenienza=Provenienza.NON_NOTA,
    )
    utente = Utente.objects.create(
        username="pres", email="p@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    IncaricoAssemblea.objects.create(
        assemblea=assemblea, avente=avente, ruolo=RuoloAssemblea.PRESIDENTE, utente=utente
    )
    return utente


class TestRighe:
    def test_ordinate_per_inizio_e_descrizione_dal_punto(self, seduta, segreteria, assemblea):
        punto = odg.aggiungi_punto(assemblea, segreteria, "Elezioni")
        programma.aggiungi_riga(seduta, segreteria, inizio=ore(10, 30), punto=punto)
        programma.aggiungi_riga(
            seduta, segreteria, inizio=ore(9), fine=ore(9, 30), attivita="Accoglienza"
        )
        righe = programma.righe(seduta)
        assert [r.descrizione for r in righe] == ["Accoglienza", "Elezioni"]

    def test_controlli(self, seduta, segreteria, assemblea):
        with pytest.raises(ValidationError):
            programma.aggiungi_riga(seduta, segreteria, inizio=ore(10), fine=ore(10), attivita="X")
        with pytest.raises(ValidationError):
            programma.aggiungi_riga(seduta, segreteria, inizio=ore(10), attivita="  ")
        with pytest.raises(ValidationError):
            programma.aggiungi_riga(seduta, segreteria, inizio=None, attivita="X")
        altra = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        punto_altrui = odg.aggiungi_punto(altra, segreteria, "Bilancio")
        with pytest.raises(ValidationError):
            programma.aggiungi_riga(seduta, segreteria, inizio=ore(10), punto=punto_altrui)

    def test_solo_gestori_e_seduta_non_chiusa(self, seduta, segreteria, assemblea, presidente):
        operatore = Utente.objects.create(username="op", email="op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        for utente in (operatore, presidente):
            with pytest.raises(PermissionDenied):
                programma.aggiungi_riga(seduta, utente, inizio=ore(9), attivita="X")
        seduta.chiusa_il = alle(18)
        seduta.save()
        with pytest.raises(ValidationError):
            programma.aggiungi_riga(seduta, segreteria, inizio=ore(9), attivita="X")

    def test_eliminando_il_punto_la_riga_resta(self, seduta, segreteria, assemblea):
        punto = odg.aggiungi_punto(assemblea, segreteria, "Elezioni")
        riga = programma.aggiungi_riga(
            seduta, segreteria, inizio=ore(10), attivita="Votazioni", punto=punto
        )
        odg.elimina_punto(punto, segreteria)
        riga.refresh_from_db()
        assert riga.punto is None and riga.descrizione == "Votazioni"


class TestInCorso:
    @pytest.fixture
    def righe(self, seduta, segreteria):
        a = programma.aggiungi_riga(seduta, segreteria, inizio=ore(9), attivita="Accoglienza")
        b = programma.aggiungi_riga(
            seduta, segreteria, inizio=ore(10), fine=ore(11), attivita="Relazione"
        )
        c = programma.aggiungi_riga(seduta, segreteria, inizio=ore(11, 30), attivita="Pranzo")
        return a, b, c

    def test_secondo_l_orologio(self, seduta, righe):
        a, b, c = righe
        elenco = programma.righe(seduta)
        assert programma.in_corso(seduta, elenco, alle(8, 59)) == set()
        # Senza ora di fine, fino all'inizio della riga successiva.
        assert programma.in_corso(seduta, elenco, alle(9, 59)) == {a.pk}
        assert programma.in_corso(seduta, elenco, alle(10)) == {b.pk}
        # Fra la fine dichiarata e la riga successiva non c'è nulla.
        assert programma.in_corso(seduta, elenco, alle(11, 15)) == set()
        # L'ultima senza fine dura fino a fine giornata.
        assert programma.in_corso(seduta, elenco, alle(23, 59)) == {c.pk}

    def test_solo_nel_giorno_della_seduta(self, seduta, righe):
        elenco = programma.righe(seduta)
        assert programma.in_corso(seduta, elenco, alle(10, giorno=GIORNO.replace(day=23))) == set()

    def test_righe_sovrapposte(self, seduta, segreteria, righe):
        _, b, _ = righe
        urne = programma.aggiungi_riga(
            seduta, segreteria, inizio=ore(10, 30), fine=ore(12), attivita="Urne aperte"
        )
        elenco = programma.righe(seduta)
        assert programma.in_corso(seduta, elenco, alle(10, 45)) == {b.pk, urne.pk}

    def test_firma_cambia_con_il_contenuto(self, seduta, segreteria, righe):
        a, _, _ = righe
        prima = programma.firma(programma.righe(seduta))
        assert prima == programma.firma(programma.righe(seduta))
        programma.modifica_riga(a, segreteria, inizio=ore(9, 15), attivita="Accoglienza")
        assert programma.firma(programma.righe(seduta)) != prima


class TestCopia:
    def test_dalla_convocazione_precedente(self, seduta, segreteria, assemblea):
        punto = odg.aggiungi_punto(assemblea, segreteria, "Elezioni")
        programma.aggiungi_riga(seduta, segreteria, inizio=ore(9), attivita="Accoglienza")
        programma.aggiungi_riga(seduta, segreteria, inizio=ore(10), punto=punto)
        seconda = Seduta.objects.create(
            assemblea=assemblea, convocazione=2, data=GIORNO.replace(day=29)
        )
        assert programma.copia_dalla_precedente(seconda, segreteria) == 2
        assert [r.descrizione for r in programma.righe(seconda)] == ["Accoglienza", "Elezioni"]
        with pytest.raises(ValidationError):
            programma.copia_dalla_precedente(seconda, segreteria)

    def test_senza_precedente(self, seduta, segreteria):
        with pytest.raises(ValidationError):
            programma.copia_dalla_precedente(seduta, segreteria)


class TestPdfEViste:
    def test_pdf(self, seduta, segreteria, assemblea):
        punto = odg.aggiungi_punto(assemblea, segreteria, "Bilancio preventivo")
        programma.aggiungi_riga(
            seduta, segreteria, inizio=ore(9), fine=ore(9, 30), attivita="Accoglienza"
        )
        programma.aggiungi_riga(seduta, segreteria, inizio=ore(10), punto=punto)
        contenuto = programma.genera_programma_pdf(seduta, segreteria)
        testo = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages)
        assert "Programma dei lavori" in testo
        assert "09:00–09:30" in testo and "Accoglienza" in testo
        assert "Bilancio preventivo" in testo and "Punto 1" in testo

    def test_pdf_non_per_il_comitato_elettorale(self, seduta, assemblea):
        operatore = Utente.objects.create(username="op", email="op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        with pytest.raises(PermissionDenied):
            programma.genera_programma_pdf(seduta, operatore)

    def test_pagine_del_gestore(self, client, seduta, segreteria, assemblea):
        client.force_login(segreteria)
        base = f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/programma/"
        client.post(base, {"inizio": "09:00", "fine": "", "attivita": "Accoglienza", "punto": ""})
        riga = seduta.programma.get()
        risposta = client.post(base, {"inizio": "10:00", "fine": "09:00", "attivita": "X"})
        assert risposta.status_code == 200 and seduta.programma.count() == 1

        client.post(f"{base}{riga.pk}/", {"inizio": "08:45", "attivita": "Registrazione"})
        riga.refresh_from_db()
        assert (riga.inizio, riga.attivita) == (ore(8, 45), "Registrazione")

        stato = client.get(f"{base}stato.json").json()
        assert set(stato) == {"in_corso", "firma"}
        pdf = client.get(f"{base}pdf/")
        assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"

        client.post(base, {"azione": "elimina", "riga": riga.pk})
        assert not seduta.programma.exists()

    def test_presidente_vede_ma_non_modifica(self, client, seduta, segreteria, presidente):
        programma.aggiungi_riga(seduta, segreteria, inizio=ore(9), attivita="Accoglienza")
        riga = seduta.programma.get()
        client.force_login(presidente)
        base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/programma/"
        pagina = client.get(base)
        assert pagina.status_code == 200 and not pagina.context["puo_modificare"]
        assert client.get(f"{base}pdf/").status_code == 200
        assert client.get(f"{base}{riga.pk}/").status_code == 403
        client.post(base, {"inizio": "10:00", "attivita": "Intrusa"})
        assert seduta.programma.count() == 1

    def test_comitato_elettorale_non_vede(self, client, seduta, assemblea):
        operatore = Utente.objects.create(
            username="op", email="op@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
        )
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        client.force_login(operatore)
        base = f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/programma/"
        assert client.get(base).status_code == 403
