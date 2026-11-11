"""Tracciato per l'app di voto e foglio presenze (apps/assemblee/file.py, D-70)."""

import io

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied
from openpyxl import load_workbook
from pypdf import PdfReader

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo, FunzioneIncarico
from apps.assemblee import elenco
from apps.assemblee import file as file_assemblea
from apps.assemblee.models import (
    Assemblea,
    IncaricoDichiarato,
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
        ("123456", "Mario", "Rossi", avellino, "mario@example.it", "3330000000"),
        ("234567", "Anna", "Bianchi", avellino, "", ""),
        ("345678", "Luca", "Verdi", ariano, "luca@example.it", "3331111111"),
    ]
    for codice, nome, cognome, gruppo, email, cell in dati:
        capo = Capo.objects.create(
            codice_socio=codice, nome=nome, cognome=cognome, email=email, cellulare=cell
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    elenco.importa_elenco(assemblea, segreteria)
    # Verdi passa da Ariano ad Avellino; un nuovo capo vota su carta.
    elenco.trasferisci(assemblea.aventi_diritto.get(cognome="Verdi"), avellino, segreteria)
    elenco.inserisci(
        assemblea,
        segreteria,
        nome="Sara",
        cognome="Neri",
        gruppo=ariano,
        provenienza=Provenienza.PASSAGGIO_CLAN,
    )
    return assemblea


class TestTracciato:
    def test_righe_solo_voto_in_app(self, assemblea):
        righe = file_assemblea.righe_tracciato(assemblea)
        assert [r[4] for r in righe] == ["Bianchi", "Rossi", "Verdi"]

    def test_contenuto_di_una_riga(self, assemblea):
        rossi = file_assemblea.righe_tracciato(assemblea)[1]
        assert rossi == [
            2027,
            2,
            123456,
            "Mario",
            "Rossi",
            "AVELLINO 1",
            None,
            None,
            "CAMPANIA",
            "RINNOVO ADESIONE",
            "mario@example.it",
            "3330000000",
            None,
            None,
            None,
            None,
            "NO",
            "SI",
            None,
        ]

    def test_trasferito_resta_nel_gruppo_di_origine(self, assemblea):
        verdi = file_assemblea.righe_tracciato(assemblea)[2]
        assert verdi[5] == "ARIANO 1"

    def test_segnaposto_se_mancano_i_recapiti(self, assemblea):
        bianchi = file_assemblea.righe_tracciato(assemblea)[0]
        assert bianchi[10:12] == ["xxx@yyy.it", "3217654321"]

    def test_passato_a_carta_esce_dal_tracciato(self, assemblea, segreteria):
        elenco.passa_a_carta(assemblea.aventi_diritto.get(cognome="Rossi"), segreteria)
        assert "Rossi" not in [r[4] for r in file_assemblea.righe_tracciato(assemblea)]

    def test_file_xlsx(self, assemblea, segreteria):
        contenuto = file_assemblea.genera_tracciato_xlsx(assemblea, segreteria)
        foglio = load_workbook(io.BytesIO(contenuto)).active
        assert foglio.title == "Sheet1"
        assert all(foglio.cell(row=r, column=1).value is None for r in range(1, 6))
        assert [c.value for c in foglio[6]] == file_assemblea.INTESTAZIONE_TRACCIATO
        assert foglio.cell(row=7, column=5).value == "Bianchi"
        assert foglio.max_row == 9

        traccia = ScaricamentoFile.objects.get()
        assert traccia.tipo == TipoFile.TRACCIATO_APP
        assert traccia.utente == segreteria
        assert traccia.numero_righe == 3

    def test_solo_i_gestori(self, assemblea):
        with pytest.raises(PermissionDenied):
            file_assemblea.genera_tracciato_xlsx(assemblea, _persona("capo@example.it"))


class TestFoglioPresenze:
    def test_raggruppato_per_gruppo_attuale_con_numero_progressivo(self, assemblea):
        gruppi = file_assemblea.gruppi_foglio_presenze(assemblea)
        assert [(nome, [(n, a.cognome) for n, a in righe]) for nome, righe in gruppi] == [
            ("ARIANO 1", [(1, "Neri")]),
            ("AVELLINO 1", [(2, "Bianchi"), (3, "Rossi"), (4, "Verdi")]),
        ]

    def test_pdf(self, assemblea, segreteria):
        contenuto = file_assemblea.genera_foglio_presenze_pdf(assemblea, segreteria)
        assert contenuto[:5] == b"%PDF-"
        pagine = [p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages]
        testo = "".join(pagine)
        assert "Neri Sara" in testo
        # Ogni gruppo inizia un foglio nuovo.
        assert len(pagine) == 2
        assert "ARIANO 1" in pagine[0] and "AVELLINO 1" not in pagine[0]
        assert "AVELLINO 1" in pagine[1]
        assert all("Foglio presenze" in pagina for pagina in pagine)
        assert "Aventi diritto: 4" in testo
        assert "mario@example.it" in testo
        assert "Firma" not in testo
        assert ScaricamentoFile.objects.get().tipo == TipoFile.FOGLIO_PRESENZE

    def test_ae_accanto_al_nome(self, assemblea, segreteria):
        aventi = assemblea.aventi_diritto
        aventi.filter(cognome="Bianchi").update(ae_zona=True)
        IncaricoDichiarato.objects.create(
            avente=aventi.get(cognome="Neri"), funzione=FunzioneIncarico.AE_GRUPPO
        )
        contenuto = file_assemblea.genera_foglio_presenze_pdf(assemblea, segreteria)
        testo = "".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages)
        assert "Bianchi Anna (AEZ)" in testo
        assert "Neri Sara (AE)" in testo
        assert "Rossi Mario (" not in testo


class TestViste:
    def test_download_tracciato(self, client, segreteria, assemblea):
        client.force_login(segreteria)
        response = client.get(f"/assemblee/{assemblea.pk}/file/tracciato-app/")
        assert response.status_code == 200
        assert "attachment" in response["Content-Disposition"]

    def test_operatore_non_scarica(self, client, assemblea):
        operatore = _persona("operatore@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        client.force_login(operatore)
        assert client.get(f"/assemblee/{assemblea.pk}/file/tracciato-app/").status_code == 403
        assert client.get(f"/assemblee/{assemblea.pk}/file/foglio-presenze/").status_code == 403
