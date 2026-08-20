"""Valutazione delle partecipazioni (D-11, D-12): perimetro permessi (mai
CG), causale obbligatoria sul respingimento, ciclo richiesta documenti →
upload → approvazione."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.contributi.models import (
    Campagna,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.contributi.valutazione import (
    approva_partecipazione,
    carica_allegato,
    respingi_partecipazione,
    richiedi_documenti,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def campagna() -> Campagna:
    c = Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )
    Campagna.objects.filter(pk=c.pk).update(stato=StatoCampagna.IN_VALUTAZIONE)
    c.refresh_from_db()
    return c


@pytest.fixture
def partecipazione(campagna, gruppo, capo, cfm) -> Partecipazione:
    p = Partecipazione(
        campagna=campagna,
        capo=capo,
        gruppo=gruppo,
        tipologia=cfm,
        data_inizio=datetime.date(2026, 6, 1),
        data_fine=datetime.date(2026, 6, 8),
        luogo="Base scout",
        quota_versata=Decimal("51.50"),
    )
    p.full_clean(exclude=["stato"])
    p.save()
    return p


@pytest.fixture
def mcz() -> Utente:
    utente = _persona("mcz@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.MCZ)
    return utente


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    utente = _persona("cg@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return utente


class TestPermessi:
    def test_cg_non_puo_approvare(self, cg_gruppo, partecipazione):
        with pytest.raises(PermissionDenied):
            approva_partecipazione(utente=cg_gruppo, partecipazione=partecipazione)

    def test_mcz_puo_approvare(self, mcz, partecipazione):
        approva_partecipazione(utente=mcz, partecipazione=partecipazione)
        partecipazione.refresh_from_db()
        assert partecipazione.stato == StatoPartecipazione.APPROVATA
        assert partecipazione.valutata_da_id == mcz.pk
        assert partecipazione.data_valutazione is not None

    def test_senza_ruolo_non_puo_valutare(self, partecipazione):
        estraneo = _persona("estraneo@campania.agesci.it")
        with pytest.raises(PermissionDenied):
            approva_partecipazione(utente=estraneo, partecipazione=partecipazione)


class TestRespingimento:
    def test_causale_obbligatoria(self, mcz, partecipazione):
        with pytest.raises(ValidationError):
            respingi_partecipazione(utente=mcz, partecipazione=partecipazione, motivazione="   ")
        partecipazione.refresh_from_db()
        assert partecipazione.stato == StatoPartecipazione.INSERITA

    def test_respingimento_con_causale(self, mcz, partecipazione):
        respingi_partecipazione(
            utente=mcz, partecipazione=partecipazione, motivazione="Documentazione insufficiente."
        )
        partecipazione.refresh_from_db()
        assert partecipazione.stato == StatoPartecipazione.RESPINTA
        assert partecipazione.motivazione_respingimento == "Documentazione insufficiente."

    def test_approvata_non_respingibile_da_valutazione_ordinaria(
        self, mcz, campagna, gruppo, capo, cfm
    ):
        # D-24: solo la disattivazione del gruppo può respingere una
        # partecipazione già APPROVATA, mai la valutazione ordinaria.
        p = Partecipazione(
            campagna=campagna,
            capo=capo,
            gruppo=gruppo,
            tipologia=cfm,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base scout",
            quota_versata=Decimal("51.50"),
            stato=StatoPartecipazione.APPROVATA,
        )
        p.full_clean(exclude=["stato"])
        p.save()

        with pytest.raises(ValidationError):
            respingi_partecipazione(utente=mcz, partecipazione=p, motivazione="Errore")
        p.refresh_from_db()
        assert p.stato == StatoPartecipazione.APPROVATA


class TestRichiestaDocumentiEAllegato:
    def test_ciclo_completo(self, mcz, cg_gruppo, partecipazione):
        richiedi_documenti(utente=mcz, partecipazione=partecipazione)
        partecipazione.refresh_from_db()
        assert partecipazione.stato == StatoPartecipazione.DOCUMENTI_RICHIESTI
        assert partecipazione.valutata_da_id is None  # non è un esito finale

        file = SimpleUploadedFile("prova.pdf", b"contenuto", content_type="application/pdf")
        allegato = carica_allegato(
            utente=cg_gruppo, partecipazione=partecipazione, file=file, tipo="Attestato"
        )
        assert allegato.caricato_da_id == cg_gruppo.pk
        partecipazione.refresh_from_db()
        assert partecipazione.stato == StatoPartecipazione.DOCUMENTI_RICHIESTI  # invariato

        approva_partecipazione(utente=mcz, partecipazione=partecipazione)
        partecipazione.refresh_from_db()
        assert partecipazione.stato == StatoPartecipazione.APPROVATA

    def test_allegato_fuori_perimetro_negato(self, mcz, partecipazione):
        richiedi_documenti(utente=mcz, partecipazione=partecipazione)
        partecipazione.refresh_from_db()
        estraneo = _persona("altro-cg@campania.agesci.it")
        altro_gruppo = Gruppo.objects.create(codice="E0199", nome="ALTRO GRUPPO")
        Ruolo.objects.create(utente=estraneo, tipo=Ruolo.Tipo.CG, gruppo=altro_gruppo)

        file = SimpleUploadedFile("prova.pdf", b"contenuto", content_type="application/pdf")
        with pytest.raises(PermissionDenied):
            carica_allegato(utente=estraneo, partecipazione=partecipazione, file=file)

    def test_allegato_senza_richiesta_negato(self, cg_gruppo, partecipazione):
        file = SimpleUploadedFile("prova.pdf", b"contenuto", content_type="application/pdf")
        with pytest.raises(ValidationError):
            carica_allegato(utente=cg_gruppo, partecipazione=partecipazione, file=file)
