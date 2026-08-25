"""Test del service layer di import PDF di autorizzazione (§6.2, D-08, D-09,
D-30, D-32, D-34): ParseResult sintetici inline, nessuna fixture PDF reale
(stesso principio di test_importazione_buonacaccia.py)."""

import datetime
import zipfile
from io import BytesIO

import pytest
from django.core import mail

from apps.accounts.models import Delega, Ruolo, TipoUtente, Utente
from apps.anagrafica.importazione_autorizzazioni import (
    PdfCaricato,
    applica_piano_autorizzazioni,
    costruisci_piano_autorizzazioni,
    estrai_pdf_da_file_caricati,
)
from apps.anagrafica.models import (
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    ImportazioneAutorizzazioni,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.anagrafica.parser.autorizzazioni import ParseResult
from apps.anagrafica.parser.buonacaccia import AVVISO, ERRORE
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026
DATA_15_GEN = datetime.datetime(2026, 1, 15)
DATA_08_MAG = datetime.datetime(2026, 5, 8)


def _record(
    *,
    codice_socio="10001",
    nome="MARIO ROSSI",
    unita="H1 BRANCO MISTO",
    branca="L/C",
    genere_unita="MISTO",
    genere="M",
    livello_foca=1,
    funzione="CAPO UNITÀ",
    anno=ANNO,
    gruppo="AVELLINO 1",
    codice_gruppo="E0133",
) -> dict:
    return {
        "codice_socio": codice_socio,
        "nome": nome,
        "gruppo": gruppo,
        "codice_gruppo": codice_gruppo,
        "unita": unita,
        "branca": branca,
        "genere_unita": genere_unita,
        "genere": genere,
        "livello_foca": livello_foca,
        "funzione": funzione,
        "anno": anno,
    }


def _parse_result(
    *,
    gruppo_codice="E0133",
    gruppo_nome="AVELLINO 1",
    anno=ANNO,
    data_aggiornamento=DATA_15_GEN,
    records=None,
) -> ParseResult:
    return ParseResult(
        data_aggiornamento=data_aggiornamento,
        anno=anno,
        gruppo_nome=gruppo_nome,
        gruppo_codice=gruppo_codice,
        records=records or [],
    )


def _pdf(nome_file="e0133.pdf", **kwargs) -> PdfCaricato:
    return PdfCaricato(
        nome_file=nome_file, contenuto=b"%PDF-fake", risultato=_parse_result(**kwargs)
    )


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo, livello_foca=5)
    return c


@pytest.fixture
def seconda_capa(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10002", nome="MARIA", cognome="BIANCHI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo, livello_foca=5)
    return c


class TestCostruisciPiano:
    def test_funzione_fuori_vocabolario_non_scritta(self, capo):
        pdf = _pdf(records=[_record(funzione="SERVIZIO DIin CSsoli R SUPPORTO AL GRUPPO")])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert piano.incarichi == []
        assert any(a.livello == ERRORE and a.campo == "Funzione" for a in piano.anomalie)

    def test_resto_del_batch_applicato_nonostante_una_riga_anomala(self, capo):
        pdf = _pdf(
            records=[
                _record(codice_socio="10001", funzione="FUNZIONE INVENTATA"),
                _record(codice_socio="10001", unita="H1 BRANCO", funzione="AIUTO CAPO UNITÀ"),
            ]
        )

        piano = costruisci_piano_autorizzazioni([pdf])

        assert len(piano.incarichi) == 1
        assert piano.incarichi[0].funzione == FunzioneIncarico.AIUTO_CAPO_UNITA

    def test_pdf_con_data_uguale_a_registrata_e_accettato(self, capo, gruppo):
        gruppo.data_autorizzazione = datetime.date(2026, 1, 15)
        gruppo.save()
        pdf = _pdf(data_aggiornamento=DATA_15_GEN, records=[_record()])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert "E0133" in piano.pdf_vincitori
        assert not any(a.campo == "Autorizzazione" for a in piano.anomalie)

    def test_pdf_con_data_precedente_a_registrata_e_rifiutato(self, capo, gruppo):
        gruppo.data_autorizzazione = datetime.date(2026, 5, 8)
        gruppo.save()
        pdf = _pdf(data_aggiornamento=DATA_15_GEN, records=[_record()])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert piano.pdf_vincitori == {}
        assert any(a.campo == "Autorizzazione" for a in piano.anomalie)

    def test_pdf_con_data_successiva_e_accettato(self, capo, gruppo):
        gruppo.data_autorizzazione = datetime.date(2025, 1, 1)
        gruppo.save()
        pdf = _pdf(data_aggiornamento=DATA_15_GEN, records=[_record()])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert "E0133" in piano.pdf_vincitori

    def test_batch_con_due_pdf_stesso_gruppo_vince_il_piu_recente(self, capo, gruppo):
        vecchio = _pdf(
            "vecchio.pdf", data_aggiornamento=DATA_15_GEN, records=[_record(livello_foca=1)]
        )
        nuovo = _pdf("nuovo.pdf", data_aggiornamento=DATA_08_MAG, records=[_record(livello_foca=3)])

        piano = costruisci_piano_autorizzazioni([vecchio, nuovo])

        assert piano.pdf_vincitori["E0133"].nome_file == "nuovo.pdf"
        assert piano.incarichi[0].livello_foca == 3

    def test_capo_assente_in_anagrafica_non_creato(self, gruppo):
        pdf = _pdf(records=[_record(codice_socio="99999")])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert piano.incarichi == []
        assert any(a.campo == "Capo" and a.codice_socio == "99999" for a in piano.anomalie)

    def test_gruppo_inesistente_va_in_anomalia(self):
        pdf = _pdf(gruppo_codice="E9999", records=[_record()])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert piano.pdf_vincitori == {}
        assert any(a.campo == "Gruppo" for a in piano.anomalie)

    def test_pdf_non_riconosciuto_va_in_anomalia(self):
        non_valido = PdfCaricato(
            "vuoto.pdf", b"", ParseResult(datetime.datetime.min, 0, "", "", [])
        )

        piano = costruisci_piano_autorizzazioni([non_valido])

        assert piano.valido is False
        assert any(a.campo == "File" for a in piano.anomalie)

    def test_caso_v1_stesso_capo_in_due_gruppi_di_servizio(self, capo, gruppo, altro_gruppo):
        pdf1 = _pdf(
            "e0133.pdf",
            gruppo_codice="E0133",
            gruppo_nome="AVELLINO 1",
            records=[_record(unita="H1 BRANCO", funzione="CAPO UNITÀ")],
        )
        pdf2 = _pdf(
            "e0134.pdf",
            gruppo_codice="E0134",
            gruppo_nome="AVELLINO 2",
            records=[_record(unita="M1 REPARTO", branca="E/G", funzione="AIUTO CAPO UNITÀ")],
        )

        piano = costruisci_piano_autorizzazioni([pdf1, pdf2])

        assert len(piano.incarichi) == 2
        assert {op.gruppo_codice for op in piano.incarichi} == {"E0133", "E0134"}

    def test_incarico_manuale_sovrascritto_segnalato_come_avviso(self, capo, gruppo):
        IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=gruppo,
            codice_unita="H1",
            nome_unita="BRANCO",
            branca="LC",
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            origine=OrigineIncarico.MANUALE,
        )
        pdf = _pdf(records=[_record(funzione="CAPO UNITÀ")])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert any(
            a.livello == AVVISO and a.campo == "Incarico manuale" and a.codice_socio == "10001"
            for a in piano.anomalie
        )
        # È solo un avviso: non impedisce l'applicazione del piano (D-32).
        assert piano.pdf_vincitori != {}

    def test_incarico_manuale_di_altro_gruppo_non_segnalato(self, capo, gruppo, altro_gruppo):
        IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=altro_gruppo,
            codice_unita="M1",
            nome_unita="REPARTO",
            branca="EG",
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            origine=OrigineIncarico.MANUALE,
        )
        pdf = _pdf(records=[_record(funzione="CAPO UNITÀ")])

        piano = costruisci_piano_autorizzazioni([pdf])

        assert not any(a.campo == "Incarico manuale" for a in piano.anomalie)


class TestApplicaPiano:
    def test_incarichi_scritti_e_batch_tracciato(self, capo, gruppo):
        pdf = _pdf(records=[_record(funzione="CAPO UNITÀ")])
        piano = costruisci_piano_autorizzazioni([pdf])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert IncaricoUnita.objects.filter(capo=capo, cessato_il__isnull=True).count() == 1
        assert ImportazioneAutorizzazioni.objects.count() == 1
        assert importazione.conteggi["incarichi_creati"] == 1
        gruppo.refresh_from_db()
        assert gruppo.data_autorizzazione == datetime.date(2026, 1, 15)

    def test_sostituzione_integrale_cessa_incarico_manuale_preesistente(self, capo, gruppo):
        vecchio = IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=gruppo,
            codice_unita="H1",
            nome_unita="BRANCO",
            branca="LC",
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            origine=OrigineIncarico.MANUALE,
        )
        pdf = _pdf(records=[_record(funzione="CAPO UNITÀ")])
        piano = costruisci_piano_autorizzazioni([pdf])

        applica_piano_autorizzazioni(piano, utente=None)

        vecchio.refresh_from_db()
        assert vecchio.cessato_il is not None
        nuovo = IncaricoUnita.objects.get(cessato_il__isnull=True)
        assert nuovo.funzione == FunzioneIncarico.CAPO_UNITA
        assert nuovo.origine == OrigineIncarico.IMPORT

    def test_derivati_ricalcolati_su_censimento(self, capo, gruppo):
        pdf = _pdf(
            records=[_record(funzione="CAPO GRUPPO", branca="Adulti", unita="G1 COMUNITA CAPI")]
        )
        piano = costruisci_piano_autorizzazioni([pdf])

        applica_piano_autorizzazioni(piano, utente=None)

        censimento = CensimentoCapo.objects.get(capo=capo, anno_scout=ANNO)
        assert censimento.is_capogruppo is True
        assert censimento.a_disposizione is False

    def test_capo_senza_utente_non_tocca_alcun_ruolo(self, capo, gruppo):
        pdf = _pdf(
            records=[_record(funzione="CAPO GRUPPO", branca="Adulti", unita="G1 COMUNITA CAPI")]
        )
        piano = costruisci_piano_autorizzazioni([pdf])

        applica_piano_autorizzazioni(piano, utente=None)

        assert Ruolo.objects.count() == 0

    def test_sincronizzazione_cg_apre_ruolo_per_capo_con_account(self, capo, gruppo):
        persona = Utente.objects.create(
            username="mario", email="mario@campania.agesci.it", tipo=TipoUtente.PERSONA
        )
        capo.utente = persona
        capo.save(update_fields=["utente"])

        pdf = _pdf(
            records=[_record(funzione="CAPO GRUPPO", branca="Adulti", unita="G1 COMUNITA CAPI")]
        )
        piano = costruisci_piano_autorizzazioni([pdf])
        applica_piano_autorizzazioni(piano, utente=None)

        ruolo = Ruolo.objects.get(utente=persona, tipo=Ruolo.Tipo.CG)
        assert ruolo.gruppo_id == gruppo.codice
        assert ruolo.origine == Ruolo.Origine.DERIVATO

    def test_sincronizzazione_cg_chiude_ruolo_e_revoca_deleghe_a_cascata(self, capo, gruppo):
        persona = Utente.objects.create(
            username="mario", email="mario@campania.agesci.it", tipo=TipoUtente.PERSONA
        )
        capo.utente = persona
        capo.save(update_fields=["utente"])
        ruolo = Ruolo.objects.create(
            utente=persona, tipo=Ruolo.Tipo.CG, gruppo=gruppo, origine=Ruolo.Origine.DERIVATO
        )
        delegato = Utente.objects.create(
            username="delegato", email="delegato@campania.agesci.it", tipo=TipoUtente.PERSONA
        )
        delega = Delega.objects.create(
            delegante=persona,
            delegato=delegato,
            ruolo=ruolo,
            data_fine=datetime.date.today() + datetime.timedelta(days=30),
        )
        mail.outbox.clear()

        # Autorizzazione senza più CAPO_GRUPPO per questo capo: solo AIUTO.
        pdf = _pdf(records=[_record(funzione="AIUTO CAPO UNITÀ")])
        piano = costruisci_piano_autorizzazioni([pdf])
        applica_piano_autorizzazioni(piano, utente=None)

        ruolo.refresh_from_db()
        delega.refresh_from_db()
        assert ruolo.attivo is False
        assert delega.attiva is False
        assert len(mail.outbox) >= 1

    def test_reimport_stesso_pdf_stessa_data_e_idempotente(self, capo, gruppo):
        """Stessa data_aggiornamento: il reimport è accettato (non scartato da
        D-09) e riapplicato senza errori, senza duplicare gli incarichi."""
        pdf1 = _pdf(records=[_record(funzione="CAPO UNITÀ")])
        piano1 = costruisci_piano_autorizzazioni([pdf1])
        applica_piano_autorizzazioni(piano1, utente=None)

        pdf2 = _pdf(records=[_record(funzione="CAPO UNITÀ")])
        piano2 = costruisci_piano_autorizzazioni([pdf2])
        assert "E0133" in piano2.pdf_vincitori

        applica_piano_autorizzazioni(piano2, utente=None)
        assert IncaricoUnita.objects.filter(cessato_il__isnull=True).count() == 1

    def test_piano_non_valido_solleva_errore(self):
        with pytest.raises(ValueError):
            applica_piano_autorizzazioni(costruisci_piano_autorizzazioni([]), utente=None)


class TestVincoloCapogruppo:
    """D-35: un solo gruppo reale per CG, 2 CG per gruppo (1M+1F)."""

    def _record_cg(self, **kwargs):
        return _record(funzione="CAPO GRUPPO", branca="Adulti", unita="G1 COMUNITA CAPI", **kwargs)

    def test_due_cg_stesso_sesso_il_secondo_non_viene_creato(self, capo, seconda_capa, gruppo):
        pdf = _pdf(
            records=[
                self._record_cg(codice_socio="10001", genere="M"),
                self._record_cg(codice_socio="10002", genere="M"),
            ]
        )
        piano = costruisci_piano_autorizzazioni([pdf])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert (
            IncaricoUnita.objects.filter(
                funzione=FunzioneIncarico.CAPO_GRUPPO, cessato_il__isnull=True
            ).count()
            == 1
        )
        assert any(
            a["livello"] == ERRORE and a["campo"] == "CapoGruppo" for a in importazione.anomalie
        )

    def test_due_cg_sessi_diversi_entrambi_creati_nessuna_anomalia(
        self, capo, seconda_capa, gruppo
    ):
        pdf = _pdf(
            records=[
                self._record_cg(codice_socio="10001", genere="M"),
                self._record_cg(codice_socio="10002", genere="F"),
            ]
        )
        piano = costruisci_piano_autorizzazioni([pdf])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert (
            IncaricoUnita.objects.filter(
                funzione=FunzioneIncarico.CAPO_GRUPPO, cessato_il__isnull=True
            ).count()
            == 2
        )
        assert not any(a["campo"] == "CapoGruppo" for a in importazione.anomalie)

    def test_un_solo_cg_produce_anomalia_non_bloccante(self, capo, gruppo):
        pdf = _pdf(records=[self._record_cg(codice_socio="10001", genere="M")])
        piano = costruisci_piano_autorizzazioni([pdf])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert (
            IncaricoUnita.objects.filter(
                funzione=FunzioneIncarico.CAPO_GRUPPO, cessato_il__isnull=True
            ).count()
            == 1
        )
        assert any(
            a["livello"] == AVVISO
            and a["campo"] == "CapoGruppo"
            and "un solo capogruppo" in a["dettaglio"]
            for a in importazione.anomalie
        )

    def test_sesso_non_riconosciuto_non_blocca_ma_segnala(self, capo, seconda_capa, gruppo):
        pdf = _pdf(
            records=[
                self._record_cg(codice_socio="10001", genere=""),
                self._record_cg(codice_socio="10002", genere=""),
            ]
        )
        piano = costruisci_piano_autorizzazioni([pdf])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert (
            IncaricoUnita.objects.filter(
                funzione=FunzioneIncarico.CAPO_GRUPPO, cessato_il__isnull=True
            ).count()
            == 2
        )
        assert not any(
            a["livello"] == ERRORE and a["campo"] == "CapoGruppo" for a in importazione.anomalie
        )

    def test_livello_foca_diverso_da_5_produce_anomalia(self, gruppo):
        c = Capo.objects.create(codice_socio="10003", nome="LUCA", cognome="VERDI")
        CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo, livello_foca=3)
        pdf = _pdf(records=[self._record_cg(codice_socio="10003", genere="M")])
        piano = costruisci_piano_autorizzazioni([pdf])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert any(
            a["campo"] == "CapoGruppo" and "Livello Fo.Ca." in a["dettaglio"]
            for a in importazione.anomalie
        )

    def test_capo_capogruppo_su_due_gruppi_reali_produce_anomalia(self, capo, gruppo, altro_gruppo):
        pdf1 = _pdf(
            "e0133.pdf",
            gruppo_codice="E0133",
            gruppo_nome="AVELLINO 1",
            records=[self._record_cg(codice_socio="10001", genere="M")],
        )
        pdf2 = _pdf(
            "e0134.pdf",
            gruppo_codice="E0134",
            gruppo_nome="AVELLINO 2",
            records=[self._record_cg(codice_socio="10001", genere="M")],
        )
        piano = costruisci_piano_autorizzazioni([pdf1, pdf2])

        importazione = applica_piano_autorizzazioni(piano, utente=None)

        assert any(
            a["campo"] == "CapoGruppo" and "più gruppi reali" in a["dettaglio"]
            for a in importazione.anomalie
        )


class TestEstraiPdfDaFileCaricati:
    @pytest.fixture(autouse=True)
    def _parse_pdf_stub(self, monkeypatch):
        """estrai_pdf_da_file_caricati chiama il parser reale: qui interessa
        solo la logica di estrazione zip/anomalie, non il parsing PDF vero e
        proprio (già coperto da test_parser_unit.py/test_parser_integration.py),
        quindi si sostituisce parse_pdf con uno stub."""
        monkeypatch.setattr(
            "apps.anagrafica.importazione_autorizzazioni.parse_pdf",
            lambda source: _parse_result(),
        )

    def test_pdf_singolo(self):
        pdf_caricati, anomalie = estrai_pdf_da_file_caricati([("e0133.pdf", b"%PDF-fake")])
        assert len(pdf_caricati) == 1
        assert anomalie == []

    def test_zip_con_voci_miste(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archivio:
            archivio.writestr("e0133.pdf", b"%PDF-fake-1")
            archivio.writestr("e0134.pdf", b"%PDF-fake-2")
            archivio.writestr("leggimi.txt", b"non un pdf")

        pdf_caricati, anomalie = estrai_pdf_da_file_caricati(
            [("autorizzazioni.zip", buffer.getvalue())]
        )

        assert len(pdf_caricati) == 2
        assert any(a.livello == AVVISO and "leggimi.txt" in a.dettaglio for a in anomalie)

    def test_zip_corrotto_non_interrompe_il_batch(self):
        pdf_caricati, anomalie = estrai_pdf_da_file_caricati(
            [("corrotto.zip", b"non uno zip valido"), ("e0133.pdf", b"%PDF-fake")]
        )

        assert len(pdf_caricati) == 1
        assert any(a.livello == ERRORE and "corrotto.zip" in a.dettaglio for a in anomalie)

    def test_pdf_illeggibile_non_interrompe_il_batch(self, monkeypatch):
        def _rompi(source):
            raise ValueError("PDF illeggibile")

        monkeypatch.setattr("apps.anagrafica.importazione_autorizzazioni.parse_pdf", _rompi)

        pdf_caricati, anomalie = estrai_pdf_da_file_caricati([("rotto.pdf", b"non un pdf reale")])

        assert pdf_caricati == []
        assert any(a.livello == ERRORE and "rotto.pdf" in a.dettaglio for a in anomalie)

    def test_estensione_non_ammessa_va_in_avviso(self):
        pdf_caricati, anomalie = estrai_pdf_da_file_caricati([("appunti.txt", b"ciao")])

        assert pdf_caricati == []
        assert any(a.livello == AVVISO for a in anomalie)
