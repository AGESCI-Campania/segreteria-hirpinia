"""Ordine del giorno e verbale dell'assemblea in PDF (odg.py, verbale.py)."""

import datetime
import io

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from pypdf import PdfReader

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, odg, sedute, verbale, votazioni
from apps.assemblee.models import Assemblea, OperatoreVoto, Seduta, TipoAssemblea, TipoVotazione
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def assemblea(segreteria) -> Assemblea:
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for i in range(5):
        capo = Capo.objects.create(codice_socio=str(i), nome="Nome", cognome=f"Capo{i}")
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


@pytest.fixture
def seduta(assemblea, segreteria) -> Seduta:
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    for avente in assemblea.aventi_diritto.all()[:4]:
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


class TestOdg:
    def test_aggiunta_ordine_e_spostamento(self, assemblea, segreteria):
        a = odg.aggiungi_punto(assemblea, segreteria, "Bilancio preventivo")
        b = odg.aggiungi_punto(assemblea, segreteria, "Varie ed eventuali")
        assert (a.ordine, b.ordine) == (1, 2)
        odg.sposta_punto(b, segreteria, su=True)
        assert list(assemblea.punti_odg.values_list("titolo", flat=True)) == [
            "Varie ed eventuali",
            "Bilancio preventivo",
        ]
        odg.elimina_punto(b, segreteria)
        a.refresh_from_db()
        assert a.ordine == 1

    def test_titolo_obbligatorio(self, assemblea, segreteria):
        with pytest.raises(ValidationError):
            odg.aggiungi_punto(assemblea, segreteria, "  ")

    def test_solo_gestori(self, assemblea):
        operatore = Utente.objects.create(username="op", email="op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        with pytest.raises(PermissionDenied):
            odg.aggiungi_punto(assemblea, operatore, "X")


class TestVerbale:
    def test_fotografia_alla_costituzione(self, seduta):
        assert (seduta.presenti_alla_costituzione, seduta.aventi_alla_costituzione) == (4, 5)
        assert seduta.presenti_app_alla_costituzione == 4

    def test_solo_per_seduta_costituita(self, assemblea, segreteria):
        with pytest.raises(ValidationError):
            verbale.contesto_verbale(assemblea.sedute.get())

    def test_pdf(self, seduta, segreteria, assemblea):
        punto = odg.aggiungi_punto(assemblea, segreteria, "Bilancio preventivo")
        odg.modifica_punto(
            punto, segreteria, titolo=punto.titolo, testo="Il tesoriere illustra il bilancio."
        )
        votazione = votazioni.apri_votazione(
            seduta, segreteria, tipo=TipoVotazione.BILANCIO, oggetto="Bilancio 2026/27", punto=punto
        )
        votazioni.registra_risultati(
            votazione,
            segreteria,
            per_canale={"PALESE": {"favorevoli": 3, "contrari": 1, "astenuti": 0}},
        )
        dati = verbale.verbale_della_seduta(seduta)
        dati.presidente = "Mario Rossi"
        dati.segretario = "Anna Bianchi"
        dati.rdz_1 = "Luca Verdi"
        dati.ora_apertura = datetime.time(9, 30)
        dati.save()

        contenuto = verbale.genera_verbale_pdf(seduta, segreteria)
        testo = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages).replace(
            "\n", " "
        )
        assert "Verbale dell'Assemblea di Zona" in testo
        assert "Mario Rossi" in testo and "Anna Bianchi" in testo
        assert "4 presenti su 5 aventi diritto" in testo
        assert "Il tesoriere illustra il bilancio." in testo
        assert "Approvata con 3 voti favorevoli" in testo
        assert "92048600644" in testo
        # Un solo RdZ indicato: una sola firma di Responsabile di Zona.
        assert testo.count("Responsabile di Zona Luca Verdi") == 1
        assert "[…]" in testo  # ora di chiusura non indicata

    def test_solo_i_gestori_scaricano(self, seduta, assemblea):
        operatore = Utente.objects.create(username="op", email="op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        with pytest.raises(PermissionDenied):
            verbale.genera_verbale_pdf(seduta, operatore)


class TestViste:
    def test_odg_e_verbale_dalle_pagine(self, client, seduta, segreteria, assemblea):
        client.force_login(segreteria)
        client.post(
            f"/assemblee/{assemblea.pk}/odg/",
            {"azione": "aggiungi", "titolo": "Varie ed eventuali"},
        )
        assert assemblea.punti_odg.get().titolo == "Varie ed eventuali"

        base = f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/verbale/"
        pagina = client.get(base)
        assert "Capo0 Nome" in pagina.context["nomi_aventi"]
        client.post(base, {"presidente": "Mario Rossi", "luogo": "Avellino"})
        assert verbale.verbale_della_seduta(seduta).presidente == "Mario Rossi"

        pdf = client.get(f"{base}pdf/")
        assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


class TestVariazioneRappresentante:
    def test_precompila_solo_da_un_rdz(self, seduta, segreteria, assemblea):
        avente = assemblea.aventi_diritto.get(codice_socio="0")
        Capo.objects.filter(pk="0").update(codice_fiscale="RSSMRA80A01A509X", cap="83100")
        variazione = verbale.variazione_della_seduta(seduta)
        with pytest.raises(ValidationError):
            verbale.precompila_rappresentante(variazione, avente, segreteria)
        avente.rdz = True
        avente.save()
        avente.refresh_from_db()
        verbale.precompila_rappresentante(variazione, avente, segreteria)
        variazione.refresh_from_db()
        assert (variazione.cognome, variazione.codice_fiscale, variazione.cap) == (
            "Capo0",
            "RSSMRA80A01A509X",
            "83100",
        )

    def test_pdf_con_e_senza_sede(self, seduta, segreteria):
        variazione = verbale.variazione_della_seduta(seduta)
        variazione.cognome, variazione.nome = "Verdi", "Luca"
        variazione.save()

        def testo() -> str:
            contenuto = verbale.genera_variazione_pdf(seduta, segreteria)
            pagine = PdfReader(io.BytesIO(contenuto)).pages
            return " ".join(p.extract_text() for p in pagine).replace("\n", " ")

        senza = testo()
        assert "Verdi Luca" in senza and "art. 24 dello Statuto" in senza
        assert "nuova sede legale" not in senza
        variazione.varia_sede = True
        variazione.sede_comune = "Avellino"
        variazione.save()
        assert "nuova sede legale" in testo()

    def test_dalle_pagine(self, client, seduta, segreteria, assemblea):
        client.force_login(segreteria)
        base = f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/verbale/rappresentante-legale/"
        assert client.get(base).status_code == 200
        client.post(base, {"cognome": "Verdi", "nome": "Luca", "provincia_nascita": "AV"})
        assert verbale.variazione_della_seduta(seduta).provincia_nascita == "AV"
        assert client.get(f"{base}pdf/").content[:5] == b"%PDF-"


def test_verifiche_nel_verbale(seduta, segreteria):
    sedute.apri_verifica(seduta, "PRESIDENZA", segreteria)
    for avente in seduta.assemblea.aventi_diritto.all()[:3]:
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.chiudi_verifica(seduta, segreteria)
    ((verifica, maggioranza),) = verbale.contesto_verbale(seduta)["verifiche"]
    assert (verifica.presenti_rilevati, verifica.quorum_raggiunto, maggioranza) == (3, True, 2)
    contenuto = verbale.genera_verbale_pdf(seduta, segreteria)
    testo = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages)
    assert "la maggioranza per le deliberazioni e le elezioni è di 2 voti" in testo.replace(
        "\n", " "
    )


def test_verbale_chiusura_per_mancanza_di_quorum(seduta, segreteria):
    sedute.apri_verifica(seduta, "CAPI", segreteria)
    sedute.registra_presenza(seduta, seduta.assemblea.aventi_diritto.first(), segreteria)
    sedute.chiudi_verifica(seduta, segreteria)
    contenuto = verbale.genera_verbale_pdf(seduta, segreteria)
    testo = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages)
    testo = testo.replace("\n", " ")
    assert "la Presidenza dichiara chiusa l'Assemblea" in testo
    assert "Null'altro essendovi da deliberare" not in testo
