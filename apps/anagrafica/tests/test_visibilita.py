"""Test di `capi_visibili()` (D-34): funzione simmetrica a `gruppi_visibili()`,
deve considerare sia il censimento sia il servizio."""

import datetime

import pytest

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.anagrafica.visibilita import capi_visibili
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str) -> Utente:
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def gruppo_a() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def gruppo_b() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def cg_gruppo_a(gruppo_a) -> Utente:
    u = _persona("cg-a@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
    return u


@pytest.fixture
def segreteria() -> Utente:
    u = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
    return u


def _capo(codice, gruppo) -> Capo:
    c = Capo.objects.create(codice_socio=codice, nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


def _incarico(capo, gruppo_servizio, *, cessato_il=None):
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=ANNO,
        gruppo_servizio=gruppo_servizio,
        codice_unita="H1",
        nome_unita="BRANCO",
        branca=BrancaUnita.LC,
        genere_unita="MISTO",
        funzione=FunzioneIncarico.CAPO_UNITA,
        origine=OrigineIncarico.IMPORT,
        cessato_il=cessato_il,
    )


class TestCapiVisibili:
    def test_cg_vede_capo_censito_nel_proprio_gruppo(self, gruppo_a, cg_gruppo_a):
        capo = _capo("10001", gruppo_a)

        visibili = capi_visibili(cg_gruppo_a, ANNO)

        assert visibili.filter(capo=capo).exists()

    def test_cg_vede_capo_censito_altrove_ma_in_servizio_nel_proprio_gruppo(
        self, gruppo_a, gruppo_b, cg_gruppo_a
    ):
        capo = _capo("10002", gruppo_b)
        _incarico(capo, gruppo_a)

        visibili = capi_visibili(cg_gruppo_a, ANNO)

        assert visibili.filter(capo=capo).exists()

    def test_cg_non_vede_capo_estraneo(self, gruppo_a, gruppo_b, cg_gruppo_a):
        capo = _capo("10003", gruppo_b)
        _incarico(capo, gruppo_b)

        visibili = capi_visibili(cg_gruppo_a, ANNO)

        assert not visibili.filter(capo=capo).exists()

    def test_incarico_cessato_non_dà_visibilità(self, gruppo_a, gruppo_b, cg_gruppo_a):
        capo = _capo("10004", gruppo_b)
        _incarico(capo, gruppo_a, cessato_il=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))

        visibili = capi_visibili(cg_gruppo_a, ANNO)

        assert not visibili.filter(capo=capo).exists()

    def test_segreteria_vede_tutta_la_zona(self, gruppo_a, gruppo_b, segreteria):
        capo_a = _capo("10005", gruppo_a)
        capo_b = _capo("10006", gruppo_b)

        visibili = capi_visibili(segreteria, ANNO)

        assert visibili.filter(capo=capo_a).exists()
        assert visibili.filter(capo=capo_b).exists()

    def test_nessun_duplicato_con_più_incarichi_nello_stesso_gruppo(self, gruppo_a, cg_gruppo_a):
        capo = _capo("10007", gruppo_a)
        _incarico(capo, gruppo_a)
        IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=gruppo_a,
            codice_unita="H2",
            nome_unita="CERCHIO",
            branca=BrancaUnita.LC,
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            origine=OrigineIncarico.IMPORT,
        )

        visibili = capi_visibili(cg_gruppo_a, ANNO)

        assert visibili.filter(capo=capo).count() == 1
