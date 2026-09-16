"""Transizioni FSM con effetti di dominio (D-37/D-38/D-39/D-40/D-35)."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django_fsm import TransitionNotAllowed

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.note_spese.models import (
    AutorizzazioneRdzConfig,
    BudgetCentroCosto,
    CategoriaSpesa,
    CentroCosto,
    Evento,
    ImpostazioniNoteSpese,
    NotaSpese,
    RigaSpesa,
    StatoNota,
)
from apps.note_spese.transizioni import (
    annulla,
    approva,
    autorizza_rdz,
    conferma_correzione,
    conferma_integrazione,
    correggi_importo_riga,
    imputa_centro_costo,
    invia_nota,
    liquida,
    prendi_in_carico,
    respingi,
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
def capo_persona() -> Capo:
    return Capo.objects.create(codice_socio="123456A", nome="Mario", cognome="Rossi")


@pytest.fixture
def capo_utente(capo_persona: Capo) -> Utente:
    return _persona("mario.rossi@example.it", codice_socio=capo_persona.pk)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def rdz_maschile(settings) -> Utente:
    utente = _persona(settings.NOTA_SPESE_RDZ_EMAIL_MASCHILE)
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
    return utente


@pytest.fixture
def rdz_femminile(settings) -> Utente:
    utente = _persona(settings.NOTA_SPESE_RDZ_EMAIL_FEMMINILE)
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
    return utente


@pytest.fixture
def evento() -> Evento:
    return Evento.objects.create(nome="Campo estivo 2027", data_inizio=datetime.date(2027, 7, 1))


@pytest.fixture
def nota_con_riga(gruppo: Gruppo, capo_persona: Capo, evento: Evento) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo_persona, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
    )
    categoria = CategoriaSpesa.objects.create(nome="Vitto test")
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("20.00")
    )
    return nota


@pytest.fixture
def capo_compilatore() -> Capo:
    return Capo.objects.create(codice_socio="999999Z", nome="Anna", cognome="Verdi")


@pytest.fixture
def utente_compilatore(capo_compilatore: Capo) -> Utente:
    """D-36: segreteria che è anche un capo censito (ha un proprio
    `codice_socio`) — deciso con Andrea che un account puramente funzionale
    senza Capo associato non può compilare per conto terzi."""
    utente = _persona("anna.verdi@campania.agesci.it", codice_socio=capo_compilatore.pk)
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def nota_conto_terzi(
    gruppo: Gruppo, capo_persona: Capo, capo_compilatore: Capo, evento: Evento
) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo_persona,
        compilatore=capo_compilatore,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico_altro="Cuoco",
    )
    categoria = CategoriaSpesa.objects.create(nome="Vitto test conto terzi")
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("20.00")
    )
    return nota


class TestInviaNota:
    def test_solo_il_beneficiario_puo_inviare(
        self, nota_con_riga: NotaSpese, segreteria: Utente
    ) -> None:
        with pytest.raises(PermissionDenied):
            invia_nota(nota_con_riga, segreteria)

    def test_senza_righe_non_si_invia(
        self, gruppo: Gruppo, capo_persona: Capo, capo_utente: Utente, evento: Evento
    ) -> None:
        nota = NotaSpese.objects.create(
            beneficiario=capo_persona,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
        )
        with pytest.raises(ValidationError):
            invia_nota(nota, capo_utente)

    def test_assegna_numero_e_anno_spesa(
        self, nota_con_riga: NotaSpese, capo_utente: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        assert nota.stato == StatoNota.INVIATA
        assert nota.anno_spesa == 2027
        assert nota.numero == "2027/0001"

    def test_numero_progressivo_per_anno(
        self, gruppo: Gruppo, capo_persona: Capo, capo_utente: Utente, evento: Evento
    ) -> None:
        for _ in range(2):
            nota = NotaSpese.objects.create(
                beneficiario=capo_persona,
                gruppo_censimento=gruppo,
                evento=evento,
                incarico_altro="Cuoco",
            )
            categoria = CategoriaSpesa.objects.create(nome=f"Vitto {nota.pk}")
            RigaSpesa.objects.create(
                nota=nota, categoria=categoria, data=datetime.date(2027, 7, 2), importo=Decimal("1")
            )
            invia_nota(nota, capo_utente)
        numeri = set(NotaSpese.objects.values_list("numero", flat=True))
        assert numeri == {"2027/0001", "2027/0002"}


class TestFlussoCompletoSenzaAutorizzazioneRdz:
    def test_bozza_a_liquidata(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        assert nota.stato == StatoNota.IN_VERIFICA
        nota = approva(nota, segreteria)
        assert nota.stato == StatoNota.APPROVATA
        nota = liquida(nota, segreteria, anno_liquidazione=2027)
        assert nota.stato == StatoNota.LIQUIDATA
        assert nota.anno_contabilizzazione == 2027

    def test_liquidata_e_terminale(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        nota = liquida(nota, segreteria, anno_liquidazione=2027)
        with pytest.raises(TransitionNotAllowed):
            nota.liquida()

    def test_sforamento_budget_non_blocca_ma_segnala(
        self,
        nota_con_riga: NotaSpese,
        capo_utente: Utente,
        segreteria: Utente,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """D-47/D-48: lo sforamento del centro di costo non impedisce la
        liquidazione, ma viene loggato (deciso con Andrea, 2026-09-16)."""
        centro = CentroCosto.objects.create(nome="Zona")
        BudgetCentroCosto.objects.create(centro_costo=centro, anno_scout=2027, importo=Decimal("1"))
        nota_con_riga.centro_costo = centro
        nota_con_riga.save()

        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        with caplog.at_level("WARNING"):
            nota = liquida(nota, segreteria, anno_liquidazione=2027)

        assert nota.stato == StatoNota.LIQUIDATA
        assert any("sfora il budget" in messaggio for messaggio in caplog.messages)

    def test_senza_sforamento_nessun_log(
        self,
        nota_con_riga: NotaSpese,
        capo_utente: Utente,
        segreteria: Utente,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        centro = CentroCosto.objects.create(nome="Zona")
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2027, importo=Decimal("100")
        )
        nota_con_riga.centro_costo = centro
        nota_con_riga.save()

        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        with caplog.at_level("WARNING"):
            nota = liquida(nota, segreteria, anno_liquidazione=2027)

        assert nota.stato == StatoNota.LIQUIDATA
        assert caplog.messages == []


class TestDaIntegrareDaConfermare:
    def test_da_integrare_non_si_sblocca_senza_nuovo_allegato(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        riga = nota.righe.get()
        nota = richiedi_integrazione(nota, segreteria, riga, "Manca lo scontrino")
        assert nota.stato == StatoNota.DA_INTEGRARE
        with pytest.raises(ValidationError):
            conferma_integrazione(nota, capo_utente)

    def test_da_integrare_si_sblocca_con_nuovo_allegato(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        riga = nota.righe.get()
        nota = richiedi_integrazione(nota, segreteria, riga, "Manca lo scontrino")
        riga.allegati.create(file="allegati_note_spese/2027/test.pdf")
        nota = conferma_integrazione(nota, capo_utente)
        assert nota.stato == StatoNota.IN_VERIFICA

    def test_da_confermare_si_sblocca_col_solo_assenso(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        riga = nota.righe.get()
        correggi_importo_riga(riga, Decimal("15.00"), segreteria)
        riga.refresh_from_db()
        assert riga.importo_originale == Decimal("20.00")
        assert riga.importo == Decimal("15.00")
        from apps.note_spese.transizioni import richiedi_conferma

        nota = richiedi_conferma(nota, segreteria, riga, "Importo corretto, confermi?")
        assert nota.stato == StatoNota.DA_CONFERMARE
        nota = conferma_correzione(nota, capo_utente)
        assert nota.stato == StatoNota.IN_VERIFICA


class TestCorreggiImportoRiga:
    def test_congela_importo_originale_solo_alla_prima_correzione(
        self, nota_con_riga: NotaSpese, segreteria: Utente
    ) -> None:
        riga = nota_con_riga.righe.get()
        correggi_importo_riga(riga, Decimal("15.00"), segreteria)
        correggi_importo_riga(riga, Decimal("10.00"), segreteria)
        riga.refresh_from_db()
        assert riga.importo_originale == Decimal("20.00")
        assert riga.importo == Decimal("10.00")


class TestRespingi:
    def test_richiede_causale(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        with pytest.raises(ValidationError):
            respingi(nota, segreteria, "")

    def test_respinta_con_causale(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = respingi(nota, segreteria, "Spesa non ammissibile")
        assert nota.stato == StatoNota.RESPINTA
        assert nota.causale_respinta == "Spesa non ammissibile"


class TestAnnulla:
    def test_capo_annulla_prima_della_presa_in_carico(
        self, nota_con_riga: NotaSpese, capo_utente: Utente
    ) -> None:
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = annulla(nota, capo_utente)
        assert nota.stato == StatoNota.ANNULLATA


class TestAutorizzazioneRdzDoppia:
    def test_serve_una_firma_m_e_una_f(
        self,
        nota_con_riga: NotaSpese,
        capo_utente: Utente,
        segreteria: Utente,
        rdz_maschile: Utente,
        rdz_femminile: Utente,
    ) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.DOPPIA}
        )
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)

        nota = autorizza_rdz(nota, rdz_maschile)
        assert nota.stato == StatoNota.APPROVATA  # una sola firma: non basta

        nota = autorizza_rdz(nota, rdz_femminile)
        assert nota.stato == StatoNota.AUTORIZZATA_RDZ

    def test_due_firme_dello_stesso_genere_non_bastano(
        self,
        nota_con_riga: NotaSpese,
        capo_utente: Utente,
        segreteria: Utente,
        rdz_maschile: Utente,
    ) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.DOPPIA}
        )
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        nota = autorizza_rdz(nota, rdz_maschile)
        nota = autorizza_rdz(nota, rdz_maschile)
        assert nota.stato == StatoNota.APPROVATA

    def test_liquida_blocca_senza_autorizzazione_rdz_richiesta(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.SINGOLA}
        )
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        with pytest.raises(ValidationError):
            liquida(nota, segreteria, anno_liquidazione=2027)


class TestAutorizzazioneRdzGenereNonRiconosciuto:
    def test_email_rdz_non_configurata_solleva_errore(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"autorizzazione_rdz": AutorizzazioneRdzConfig.SINGOLA}
        )
        rdz_non_riconosciuto = _persona("altro@example.it")
        Ruolo.objects.create(utente=rdz_non_riconosciuto, tipo=Ruolo.Tipo.RDZ)
        nota = invia_nota(nota_con_riga, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        with pytest.raises(ValidationError):
            autorizza_rdz(nota, rdz_non_riconosciuto)


class TestCompilazionePerContoTerzi:
    """D-36: segreteria/RdZ/admin possono agire lato capo su una nota
    intestata a un altro beneficiario, se registrati come `compilatore`."""

    def test_il_compilatore_puo_inviare_la_nota(
        self, nota_conto_terzi: NotaSpese, utente_compilatore: Utente
    ) -> None:
        nota = invia_nota(nota_conto_terzi, utente_compilatore)
        assert nota.stato == StatoNota.INVIATA

    def test_il_beneficiario_puo_ancora_inviare_la_nota_compilata_per_lui(
        self, nota_conto_terzi: NotaSpese, capo_utente: Utente
    ) -> None:
        nota = invia_nota(nota_conto_terzi, capo_utente)
        assert nota.stato == StatoNota.INVIATA

    def test_un_terzo_senza_relazione_con_la_nota_non_puo_inviare(
        self, nota_conto_terzi: NotaSpese, segreteria: Utente
    ) -> None:
        with pytest.raises(PermissionDenied):
            invia_nota(nota_conto_terzi, segreteria)

    def test_codice_socio_coincidente_ma_senza_ruolo_di_gestione_non_basta(
        self, nota_conto_terzi: NotaSpese, capo_compilatore: Capo
    ) -> None:
        """Difesa in profondità: il solo `codice_socio` coincidente col
        `compilatore` non basta se l'account non ha (più) un ruolo di
        gestione — coerente con la decisione presa con Andrea che il
        compilatore per conto terzi deve sempre essere segreteria/RdZ/admin."""
        utente_senza_ruolo = _persona(
            "anna.verdi.senza-ruolo@example.it", codice_socio=capo_compilatore.pk
        )
        with pytest.raises(PermissionDenied):
            invia_nota(nota_conto_terzi, utente_senza_ruolo)

    def test_il_compilatore_puo_annullare_la_nota(
        self, nota_conto_terzi: NotaSpese, utente_compilatore: Utente
    ) -> None:
        nota = annulla(nota_conto_terzi, utente_compilatore)
        assert nota.stato == StatoNota.ANNULLATA


class TestImputaCentroCosto:
    def test_segreteria_puo_imputare(self, nota_con_riga: NotaSpese, segreteria: Utente) -> None:
        centro = CentroCosto.objects.create(nome="Zona")
        nota = imputa_centro_costo(nota_con_riga, segreteria, centro)
        assert nota.centro_costo_id == centro.pk

    def test_il_beneficiario_non_puo_imputare(
        self, nota_con_riga: NotaSpese, capo_utente: Utente
    ) -> None:
        centro = CentroCosto.objects.create(nome="Zona")
        with pytest.raises(PermissionDenied):
            imputa_centro_costo(nota_con_riga, capo_utente, centro)

    def test_non_si_puo_cambiare_dopo_la_liquidazione(
        self, nota_con_riga: NotaSpese, capo_utente: Utente, segreteria: Utente
    ) -> None:
        centro = CentroCosto.objects.create(nome="Zona")
        nota = imputa_centro_costo(nota_con_riga, segreteria, centro)
        nota = invia_nota(nota, capo_utente)
        nota = prendi_in_carico(nota, segreteria)
        nota = approva(nota, segreteria)
        nota = liquida(nota, segreteria, anno_liquidazione=2027)

        altro_centro = CentroCosto.objects.create(nome="Altra zona")
        with pytest.raises(ValidationError):
            imputa_centro_costo(nota, segreteria, altro_centro)
