"""Derivazioni condivise fra import PDF e assegnazione manuale (D-08, D-31)."""

import pytest
from django.utils import timezone

from apps.anagrafica.derivazioni import ricalcola_derivati_capo, ricalcola_pattuglia
from apps.anagrafica.models import (
    Branca,
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    MembroPattuglia,
    OrigineIncarico,
    Pattuglia,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=2026, gruppo=gruppo)
    return c


def _incarico(
    capo,
    gruppo,
    *,
    funzione,
    branca=BrancaUnita.LC,
    codice_unita="H1",
    cessato_il=None,
    origine=OrigineIncarico.IMPORT,
):
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=2026,
        gruppo_servizio=gruppo,
        codice_unita=codice_unita,
        nome_unita="BRANCO",
        branca=branca,
        genere_unita="MISTO",
        funzione=funzione,
        origine=origine,
        cessato_il=cessato_il,
    )


class TestRicalcolaDerivatiCapo:
    def test_none_se_capo_non_censito_nellanno(self, capo):
        assert ricalcola_derivati_capo(capo.codice_socio, 2099) is None

    def test_a_disposizione_true_senza_incarichi(self, capo):
        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)
        assert censimento.a_disposizione is True
        assert censimento.is_capogruppo is False

    def test_a_disposizione_false_con_incarico_in_gruppo_diverso_dal_censimento(
        self, capo, altro_gruppo
    ):
        """D-34: a_disposizione considera TUTTI i gruppi di servizio, non solo
        quello di censimento."""
        _incarico(capo, altro_gruppo, funzione=FunzioneIncarico.CAPO_UNITA, branca=BrancaUnita.EG)

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.a_disposizione is False
        assert censimento.branca == Branca.EG

    def test_incarico_cessato_non_conta(self, capo, gruppo):
        _incarico(capo, gruppo, funzione=FunzioneIncarico.CAPO_UNITA, cessato_il=timezone.now())

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.a_disposizione is True

    def test_is_capogruppo_true_con_incarico_capo_gruppo(self, capo, gruppo):
        _incarico(capo, gruppo, funzione=FunzioneIncarico.CAPO_GRUPPO, branca=BrancaUnita.ADULTI)

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.is_capogruppo is True

    def test_is_capogruppo_azzerato_se_incarico_rimosso(self, capo, gruppo):
        CensimentoCapo.objects.filter(capo=capo, anno_scout=2026).update(is_capogruppo=True)

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.is_capogruppo is False

    def test_priorita_branca_lc_su_eg(self, capo, gruppo, altro_gruppo):
        _incarico(
            capo,
            gruppo,
            funzione=FunzioneIncarico.CAPO_UNITA,
            branca=BrancaUnita.LC,
            codice_unita="H1",
        )
        _incarico(
            capo,
            altro_gruppo,
            funzione=FunzioneIncarico.CAPO_UNITA,
            branca=BrancaUnita.EG,
            codice_unita="M1",
        )

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.branca == Branca.LC

    def test_branca_sg_per_supporto_gruppo(self, capo, gruppo):
        _incarico(
            capo,
            gruppo,
            funzione=FunzioneIncarico.SUPPORTO_GRUPPO,
            branca=BrancaUnita.ADULTI,
            codice_unita="G1",
        )

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.branca == Branca.SG

    def test_branca_ae_per_assistente_ecclesiastico(self, capo, gruppo):
        _incarico(
            capo,
            gruppo,
            funzione=FunzioneIncarico.AE_GRUPPO,
            branca=BrancaUnita.ADULTI,
            codice_unita="G1",
        )

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.branca == Branca.AE

    def test_branca_invariata_se_nessuna_corrispondenza(self, capo, gruppo):
        CensimentoCapo.objects.filter(capo=capo, anno_scout=2026).update(branca=Branca.LC)
        _incarico(
            capo,
            gruppo,
            funzione=FunzioneIncarico.MAESTRO_NOVIZI,
            branca=BrancaUnita.LC,
            codice_unita="H1",
        )

        censimento = ricalcola_derivati_capo(capo.codice_socio, 2026)

        assert censimento.branca == Branca.LC


class TestRicalcolaPattuglia:
    def test_ignora_branche_non_ammesse(self):
        ricalcola_pattuglia(Branca.SG, 2026)
        ricalcola_pattuglia(Branca.AE, 2026)
        assert Pattuglia.objects.count() == 0

    def test_popola_pattuglia_da_censimenti(self, capo, gruppo):
        CensimentoCapo.objects.filter(capo=capo, anno_scout=2026).update(branca=Branca.LC)

        ricalcola_pattuglia(Branca.LC, 2026)

        pattuglia = Pattuglia.objects.get(branca=Branca.LC, anno_scout=2026)
        assert MembroPattuglia.objects.filter(pattuglia=pattuglia, capo=capo).exists()

    def test_rimuove_membri_non_piu_di_quella_branca(self, capo, gruppo):
        CensimentoCapo.objects.filter(capo=capo, anno_scout=2026).update(branca=Branca.LC)
        ricalcola_pattuglia(Branca.LC, 2026)

        CensimentoCapo.objects.filter(capo=capo, anno_scout=2026).update(branca=Branca.EG)
        ricalcola_pattuglia(Branca.LC, 2026)

        pattuglia = Pattuglia.objects.get(branca=Branca.LC, anno_scout=2026)
        assert not MembroPattuglia.objects.filter(pattuglia=pattuglia, capo=capo).exists()
