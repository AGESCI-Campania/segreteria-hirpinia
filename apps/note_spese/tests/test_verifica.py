"""F6e: vista di verifica con eccezioni (incarico D-50, doppioni D-57,
capienza indicativa D-48)."""

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.note_spese.models import (
    BudgetCentroCosto,
    CategoriaSpesa,
    CentroCosto,
    Evento,
    Localita,
    NotaSpese,
    RigaSpesa,
    RigaSpesaPasseggero,
    StatoNota,
)
from apps.note_spese.verifica import eccezioni_nota, note_in_verifica
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
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


@pytest.fixture
def categoria() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(nome="Vitto test verifica", richiede_allegato=False)


@pytest.fixture
def categoria_chilometrica() -> CategoriaSpesa:
    return CategoriaSpesa.objects.create(
        nome="Auto test verifica",
        tipo_calcolo="CHILOMETRICO",
        sottotipo_chilometrico="ALTRO",
    )


@pytest.fixture
def incarico(gruppo: Gruppo, capo: Capo) -> IncaricoUnita:
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=2026,
        gruppo_servizio=gruppo,
        codice_unita="R1",
        branca=BrancaUnita.RS,
        funzione=FunzioneIncarico.CAPO_UNITA,
        origine=OrigineIncarico.MANUALE,
    )


def _nota_in_verifica(
    gruppo, capo, evento, categoria, *, incarico=None, incarico_altro="Cuoco", centro_costo=None
) -> NotaSpese:
    nota = NotaSpese.objects.create(
        beneficiario=capo,
        gruppo_censimento=gruppo,
        evento=evento,
        incarico=incarico,
        incarico_altro="" if incarico else incarico_altro,
        centro_costo=centro_costo,
        stato=StatoNota.IN_VERIFICA,
        anno_spesa=2026,
    )
    RigaSpesa.objects.create(
        nota=nota, categoria=categoria, data=datetime.date(2026, 7, 2), importo=Decimal("10")
    )
    return nota


class TestNoteInVerifica:
    def test_include_solo_stati_in_lavorazione(self, gruppo, capo, evento, categoria) -> None:
        in_verifica = _nota_in_verifica(gruppo, capo, evento, categoria)
        bozza = NotaSpese.objects.create(
            beneficiario=capo, gruppo_censimento=gruppo, evento=evento, incarico_altro="Cuoco"
        )
        liquidata = NotaSpese.objects.create(
            beneficiario=capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            stato=StatoNota.LIQUIDATA,
        )

        segreteria = _persona("seg@campania.agesci.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)

        risultato = list(note_in_verifica(segreteria))

        assert in_verifica in risultato
        assert bozza not in risultato
        assert liquidata not in risultato

    def test_capo_qualsiasi_non_vede_nulla(self, gruppo, capo, evento, categoria) -> None:
        _nota_in_verifica(gruppo, capo, evento, categoria)
        Capo.objects.create(codice_socio="999999Z", nome="Luigi", cognome="Bianchi")
        altro_capo_utente = _persona("altro@example.it", codice_socio="999999Z")
        assert list(note_in_verifica(altro_capo_utente)) == []


class TestEccezioniNota:
    def test_incarico_strutturato_nessuna_eccezione(
        self, gruppo, capo, evento, categoria, incarico
    ) -> None:
        nota = _nota_in_verifica(gruppo, capo, evento, categoria, incarico=incarico)
        eccezioni = eccezioni_nota(nota)
        assert eccezioni.incarico_non_strutturato is False
        assert eccezioni.ha_eccezioni is False

    def test_incarico_altro_e_eccezione(self, gruppo, capo, evento, categoria) -> None:
        nota = _nota_in_verifica(gruppo, capo, evento, categoria)
        eccezioni = eccezioni_nota(nota)
        assert eccezioni.incarico_non_strutturato is True
        assert eccezioni.ha_eccezioni is True

    def test_nessun_centro_costo_nessuna_capienza_calcolata(
        self, gruppo, capo, evento, categoria
    ) -> None:
        nota = _nota_in_verifica(gruppo, capo, evento, categoria)
        eccezioni = eccezioni_nota(nota)
        assert eccezioni.capienza is None
        assert eccezioni.capienza_sforata is False

    def test_capienza_sforata_su_impegnato_di_unaltra_nota(
        self, gruppo, capo, evento, categoria
    ) -> None:
        """D-48: l'impegnato conta le altre note APPROVATA/AUTORIZZATA_RDZ
        dello stesso centro/anno_spesa, non la nota in verifica stessa (non
        ancora approvata) — qui una nota già approvata da 120 sfora da sola
        il budget di 100, indipendentemente dalla nota sotto verifica."""
        centro = CentroCosto.objects.create(nome="Zona")
        BudgetCentroCosto.objects.create(
            centro_costo=centro, anno_scout=2026, importo=Decimal("100")
        )
        altro_capo = Capo.objects.create(codice_socio="777777C", nome="Anna", cognome="Verdi")
        nota_approvata = NotaSpese.objects.create(
            beneficiario=altro_capo,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            centro_costo=centro,
            stato=StatoNota.APPROVATA,
            anno_spesa=2026,
        )
        RigaSpesa.objects.create(
            nota=nota_approvata,
            categoria=categoria,
            data=datetime.date(2026, 7, 2),
            importo=Decimal("120"),
        )

        nota = _nota_in_verifica(gruppo, capo, evento, categoria, centro_costo=centro)

        eccezioni = eccezioni_nota(nota)

        assert eccezioni.capienza is not None
        assert eccezioni.capienza.impegnato == Decimal("120")
        assert eccezioni.capienza.residuo_indicativo == Decimal("-20")
        assert eccezioni.capienza_sforata is True

    def test_doppione_targa_rilevato(self, gruppo, evento, categoria_chilometrica) -> None:
        avellino = Localita.objects.create(
            nome="Avellino verifica", latitudine=Decimal("40.9"), longitudine=Decimal("14.7")
        )
        napoli = Localita.objects.create(
            nome="Napoli verifica", latitudine=Decimal("40.8"), longitudine=Decimal("14.2")
        )
        guidatore = Capo.objects.create(codice_socio="333333D", nome="Mario", cognome="Rossi")
        passeggero = Capo.objects.create(codice_socio="444444E", nome="Luigi", cognome="Bianchi")

        nota = NotaSpese.objects.create(
            beneficiario=guidatore,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
            stato=StatoNota.IN_VERIFICA,
            anno_spesa=2026,
        )
        riga = RigaSpesa.objects.create(
            nota=nota,
            categoria=categoria_chilometrica,
            data=datetime.date(2026, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )
        RigaSpesaPasseggero.objects.create(riga=riga, capo=passeggero)

        altra_nota = NotaSpese.objects.create(
            beneficiario=passeggero,
            gruppo_censimento=gruppo,
            evento=evento,
            incarico_altro="Cuoco",
        )
        RigaSpesa.objects.create(
            nota=altra_nota,
            categoria=categoria_chilometrica,
            data=datetime.date(2026, 7, 2),
            localita_partenza=avellino,
            localita_arrivo=napoli,
            targa="AB123CD",
        )

        eccezioni = eccezioni_nota(nota)

        assert len(eccezioni.doppioni_targa) == 1
        assert eccezioni.ha_eccezioni is True


class TestNotaVerificaListaView:
    def test_capo_qualsiasi_non_accede(self, client, capo_utente) -> None:
        client.force_login(capo_utente)
        response = client.get("/note-spese/verifica/")
        assert response.status_code == 403

    def test_segreteria_accede_e_vede_le_eccezioni(
        self, client, segreteria, gruppo, capo, evento, categoria
    ) -> None:
        _nota_in_verifica(gruppo, capo, evento, categoria)
        client.force_login(segreteria)
        response = client.get("/note-spese/verifica/")
        assert response.status_code == 200
        assert len(response.context["righe"]) == 1
        assert response.context["righe"][0].incarico_non_strutturato is True

    def test_filtro_solo_eccezioni(
        self, client, segreteria, gruppo, capo, evento, categoria, incarico
    ) -> None:
        _nota_in_verifica(gruppo, capo, evento, categoria, incarico=incarico)
        client.force_login(segreteria)
        response = client.get("/note-spese/verifica/?solo_eccezioni=1")
        assert response.status_code == 200
        assert response.context["righe"] == []
