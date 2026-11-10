"""Email degli aventi diritto: campo, precompilazione, Excel per gruppo
(apps/assemblee/email_aventi.py, fase V0 del voto elettronico)."""

import io

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from openpyxl import load_workbook

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, email_aventi
from apps.assemblee import file as file_assemblea
from apps.assemblee.models import (
    Assemblea,
    ImportazioneEmail,
    OperatoreVoto,
    Provenienza,
    ScaricamentoFile,
    TipoAssemblea,
    TipoFile,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, ruolo: str | None = None) -> Utente:
    n = Utente.objects.count()
    utente = Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    return _persona("segreteria@campania.agesci.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def avellino() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def ariano() -> Gruppo:
    return Gruppo.objects.create(codice="E2913", nome="ARIANO 1")


@pytest.fixture
def assemblea(segreteria, avellino, ariano) -> Assemblea:
    dati = [
        ("123456", "Mario", "Rossi", avellino, "mario@example.it"),
        ("234567", "Anna", "Bianchi", avellino, ""),
        ("345678", "Luca", "Verdi", ariano, "luca@example.it"),
    ]
    for codice, nome, cognome, gruppo, email in dati:
        capo = Capo.objects.create(codice_socio=codice, nome=nome, cognome=cognome, email=email)
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _avente(assemblea, cognome):
    return assemblea.aventi_diritto.get(cognome=cognome)


def _excel(assemblea, gruppo, utente) -> bytes:
    return email_aventi.genera_excel_gruppo(assemblea, gruppo, utente)


def _modifica(contenuto: bytes, modifiche: dict[str, str]) -> bytes:
    """Riscrive la colonna Email per cognome, come farebbe un capogruppo."""
    cartella = load_workbook(io.BytesIO(contenuto))
    foglio = cartella[email_aventi.FOGLIO]
    for riga in foglio.iter_rows(min_row=email_aventi.RIGA_INTESTAZIONE + 1):
        if riga[1].value in modifiche:
            riga[4].value = modifiche[riga[1].value]
    buffer = io.BytesIO()
    cartella.save(buffer)
    return buffer.getvalue()


class TestCampoEmail:
    def test_import_dell_elenco_precompila_dall_anagrafica(self, assemblea):
        assert _avente(assemblea, "Rossi").email == "mario@example.it"
        assert _avente(assemblea, "Bianchi").email == ""

    def test_inserimento_manuale_con_email(self, assemblea, segreteria, ariano):
        avente = elenco.inserisci(
            assemblea,
            segreteria,
            nome="Sara",
            cognome="Neri",
            gruppo=ariano,
            provenienza=Provenienza.NUOVO_INGRESSO,
            email=" sara@example.it ",
        )
        assert avente.email == "sara@example.it"

    def test_inserimento_con_codice_socio_usa_l_email_dell_anagrafica(self, segreteria, avellino):
        Capo.objects.create(codice_socio="999", nome="Pia", cognome="Gialli", email="p@x.it")
        assemblea = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        avente = elenco.inserisci(
            assemblea,
            segreteria,
            nome="Pia",
            cognome="Gialli",
            gruppo=avellino,
            provenienza=Provenienza.RIENTRO,
            codice_socio="999",
        )
        assert avente.email == "p@x.it"

    def test_aggiorna_email_non_tocca_l_anagrafica(self, assemblea, segreteria):
        rossi = _avente(assemblea, "Rossi")
        assert elenco.aggiorna_email(rossi, "Mario.Rossi@Example.it ", segreteria)
        rossi.refresh_from_db()
        assert rossi.email == "mario.rossi@example.it"
        assert Capo.objects.get(pk="123456").email == "mario@example.it"
        assert not elenco.aggiorna_email(rossi, "mario.rossi@example.it", segreteria)

    def test_aggiorna_email_dall_operatore_al_banco(self, assemblea):
        operatore = _persona("op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        assert elenco.aggiorna_email(_avente(assemblea, "Bianchi"), "a@example.it", operatore)

    def test_aggiorna_email_rifiuta_chi_non_opera(self, assemblea):
        with pytest.raises(PermissionDenied):
            elenco.aggiorna_email(_avente(assemblea, "Rossi"), "x@example.it", _persona("n@x.it"))

    def test_aggiorna_email_non_valida(self, assemblea, segreteria):
        with pytest.raises(ValidationError):
            elenco.aggiorna_email(_avente(assemblea, "Rossi"), "non-una-email", segreteria)

    def test_il_tracciato_usa_l_email_dell_assemblea(self, assemblea, segreteria):
        elenco.aggiorna_email(_avente(assemblea, "Bianchi"), "anna@example.it", segreteria)
        righe = {r[4]: r for r in file_assemblea.righe_tracciato(assemblea)}
        assert righe["Bianchi"][10] == "anna@example.it"
        assert righe["Rossi"][10] == "mario@example.it"


class TestExport:
    def test_un_file_per_gruppo_con_id_nascosto(self, assemblea, segreteria, avellino):
        contenuto = _excel(assemblea, avellino, segreteria)
        foglio = load_workbook(io.BytesIO(contenuto))[email_aventi.FOGLIO]
        assert foglio["B2"].value == avellino.codice
        assert foglio.column_dimensions["A"].hidden
        cognomi = [r[1].value for r in foglio.iter_rows(min_row=email_aventi.RIGA_INTESTAZIONE + 1)]
        assert cognomi == ["Bianchi", "Rossi"]
        scaricamento = ScaricamentoFile.objects.get(assemblea=assemblea)
        assert (scaricamento.tipo, scaricamento.numero_righe) == (TipoFile.EMAIL_GRUPPO, 2)

    def test_zip_con_tutti_i_gruppi(self, assemblea, segreteria):
        import zipfile

        archivio = zipfile.ZipFile(
            io.BytesIO(email_aventi.genera_zip_gruppi(assemblea, segreteria))
        )
        assert len(archivio.namelist()) == 2

    def test_solo_i_gestori_esportano(self, assemblea, avellino):
        with pytest.raises(PermissionDenied):
            _excel(assemblea, avellino, _persona("n@x.it"))


class TestImport:
    def test_anteprima_non_scrive(self, assemblea, segreteria, avellino):
        contenuto = _modifica(_excel(assemblea, avellino, segreteria), {"Bianchi": "anna@x.it"})
        anteprima = email_aventi.anteprima_import(assemblea, email_aventi.leggi_excel(contenuto))
        assert not anteprima.bloccata
        assert [(m.avente.cognome, m.nuova) for m in anteprima.modifiche] == [
            ("Bianchi", "anna@x.it")
        ]
        assert anteprima.invariate == 1
        assert _avente(assemblea, "Bianchi").email == ""

    def test_applica_ed_e_idempotente(self, assemblea, segreteria, avellino):
        contenuto = _modifica(_excel(assemblea, avellino, segreteria), {"Bianchi": "anna@x.it"})
        prima = email_aventi.applica_import(assemblea, contenuto, "a.xlsx", segreteria)
        seconda = email_aventi.applica_import(assemblea, contenuto, "a.xlsx", segreteria)
        assert (prima.email_aggiornate, seconda.email_aggiornate) == (1, 0)
        assert _avente(assemblea, "Bianchi").email == "anna@x.it"
        assert ImportazioneEmail.objects.count() == 2

    def test_cella_vuota_non_cancella(self, assemblea, segreteria, avellino):
        contenuto = _modifica(_excel(assemblea, avellino, segreteria), {"Rossi": None})
        email_aventi.applica_import(assemblea, contenuto, "a.xlsx", segreteria)
        assert _avente(assemblea, "Rossi").email == "mario@example.it"

    def test_email_diversa_dall_anagrafica_e_solo_un_avviso(self, assemblea, segreteria, avellino):
        contenuto = _modifica(_excel(assemblea, avellino, segreteria), {"Rossi": "m@nuovo.it"})
        importazione = email_aventi.applica_import(assemblea, contenuto, "a.xlsx", segreteria)
        assert importazione.email_aggiornate == 1
        assert [a["bloccante"] for a in importazione.anomalie] == [False]
        assert "Email diversa" in email_aventi.report_csv(importazione)

    def test_email_non_valida_blocca(self, assemblea, segreteria, avellino):
        contenuto = _modifica(_excel(assemblea, avellino, segreteria), {"Bianchi": "anna@"})
        with pytest.raises(ValidationError):
            email_aventi.applica_import(assemblea, contenuto, "a.xlsx", segreteria)
        assert _avente(assemblea, "Bianchi").email == ""

    def test_riga_di_un_altro_gruppo_blocca(self, assemblea, segreteria, avellino, ariano):
        # Il file di Avellino con dentro Verdi, che è di Ariano.
        contenuto = _excel(assemblea, avellino, segreteria)
        cartella = load_workbook(io.BytesIO(contenuto))
        foglio = cartella[email_aventi.FOGLIO]
        verdi = _avente(assemblea, "Verdi")
        foglio.append([verdi.pk, "Verdi", "Luca", "345678", "luca@nuovo.it"])
        buffer = io.BytesIO()
        cartella.save(buffer)
        anteprima = email_aventi.anteprima_import(
            assemblea, email_aventi.leggi_excel(buffer.getvalue())
        )
        assert anteprima.bloccata
        assert "non è del gruppo" in anteprima.anomalie[0].messaggio

    def test_id_manomesso_blocca(self, assemblea, segreteria, avellino):
        contenuto = _excel(assemblea, avellino, segreteria)
        cartella = load_workbook(io.BytesIO(contenuto))
        foglio = cartella[email_aventi.FOGLIO]
        riga = email_aventi.RIGA_INTESTAZIONE + 1
        foglio.cell(row=riga, column=1, value=_avente(assemblea, "Rossi").pk)  # riga di Bianchi
        buffer = io.BytesIO()
        cartella.save(buffer)
        anteprima = email_aventi.anteprima_import(
            assemblea, email_aventi.leggi_excel(buffer.getvalue())
        )
        assert anteprima.bloccata
        assert "non corrispondono" in anteprima.anomalie[0].messaggio

    def test_file_non_excel(self, assemblea):
        anteprima = email_aventi.anteprima_import(
            assemblea, email_aventi.leggi_excel(b"non sono un excel")
        )
        assert anteprima.bloccata and anteprima.errore

    def test_assemblea_conclusa(self, assemblea, segreteria, avellino):
        from django.utils import timezone

        contenuto = _excel(assemblea, avellino, segreteria)
        assemblea.conclusa_il = timezone.now()
        assemblea.save()
        with pytest.raises(ValidationError):
            email_aventi.applica_import(assemblea, contenuto, "a.xlsx", segreteria)


class TestViste:
    def test_flusso_completo(self, client, assemblea, segreteria, avellino):
        client.force_login(segreteria)
        assert client.get(f"/assemblee/{assemblea.pk}/email/").status_code == 200
        risposta = client.get(f"/assemblee/{assemblea.pk}/email/gruppi/{avellino.pk}.xlsx")
        assert risposta.status_code == 200
        contenuto = _modifica(risposta.content, {"Bianchi": "anna@x.it"})
        file = io.BytesIO(contenuto)
        file.name = "avellino.xlsx"
        anteprima = client.post(
            f"/assemblee/{assemblea.pk}/email/import/anteprima/", {"file": file}
        )
        assert b"anna@x.it" in anteprima.content
        assert _avente(assemblea, "Bianchi").email == ""
        client.post(f"/assemblee/{assemblea.pk}/email/import/conferma/")
        assert _avente(assemblea, "Bianchi").email == "anna@x.it"

    def test_conferma_senza_anteprima(self, client, assemblea, segreteria):
        client.force_login(segreteria)
        risposta = client.post(f"/assemblee/{assemblea.pk}/email/import/conferma/")
        assert risposta.status_code == 302
        assert not ImportazioneEmail.objects.exists()

    def test_pagina_email_avente_per_l_operatore(self, client, assemblea):
        operatore = _persona("op@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        client.force_login(operatore)
        bianchi = _avente(assemblea, "Bianchi")
        url = f"/assemblee/{assemblea.pk}/elenco/{bianchi.pk}/email/"
        assert client.get(url).status_code == 200
        client.post(url, {"email": "anna@x.it"})
        bianchi.refresh_from_db()
        assert bianchi.email == "anna@x.it"
        # L'operatore non scarica gli Excel dei gruppi.
        assert client.get(f"/assemblee/{assemblea.pk}/email/").status_code == 403
