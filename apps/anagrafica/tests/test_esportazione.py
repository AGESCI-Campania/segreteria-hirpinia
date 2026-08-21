"""Test del service layer dell'export anagrafica (M8, D-23)."""

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.esportazione import (
    FiltriEsportazione,
    colonne_per_profilo,
    etichetta_unita,
    genera_righe_esportazione,
    ordina_per_raggruppamento,
    raggruppa_righe,
)
from apps.anagrafica.models import (
    A_DISPOSIZIONE,
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
    ProfiloColonneEsportazione,
    RaggruppamentoEsportazione,
    StatoFiltroEsportazione,
)
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


def _capo(codice, gruppo, *, attivo=True, livello_foca=None, cognome="ROSSI", nome="MARIO") -> Capo:
    c = Capo.objects.create(codice_socio=codice, nome=nome, cognome=cognome, attivo=attivo)
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo, livello_foca=livello_foca)
    return c


def _incarico(capo, gruppo_servizio, *, codice_unita="H1", funzione=FunzioneIncarico.CAPO_UNITA):
    return IncaricoUnita.objects.create(
        capo=capo,
        anno_scout=ANNO,
        gruppo_servizio=gruppo_servizio,
        codice_unita=codice_unita,
        nome_unita="BRANCO",
        branca=BrancaUnita.LC,
        genere_unita="MISTO",
        funzione=funzione,
        origine=OrigineIncarico.IMPORT,
    )


class TestPerimetro:
    def test_cg_non_puo_filtrare_su_gruppo_fuori_perimetro(self, gruppo_a, gruppo_b, cg_gruppo_a):
        filtri = FiltriEsportazione(anno_scout=ANNO, gruppo=(gruppo_b.codice,))
        with pytest.raises(PermissionDenied):
            genera_righe_esportazione(cg_gruppo_a, filtri)

    def test_cg_vede_solo_il_proprio_perimetro_senza_filtro(self, gruppo_a, gruppo_b, cg_gruppo_a):
        _capo("10001", gruppo_a)
        _capo("10002", gruppo_b)

        righe = genera_righe_esportazione(cg_gruppo_a, FiltriEsportazione(anno_scout=ANNO))

        assert {r.codice_socio for r in righe} == {"10001"}

    def test_segreteria_vede_tutta_la_zona(self, gruppo_a, gruppo_b, segreteria):
        _capo("10001", gruppo_a)
        _capo("10002", gruppo_b)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert {r.codice_socio for r in righe} == {"10001", "10002"}


class TestRighe:
    def test_capo_con_più_incarichi_genera_più_righe(self, gruppo_a, segreteria):
        capo = _capo("10001", gruppo_a)
        _incarico(capo, gruppo_a, codice_unita="H1")
        _incarico(capo, gruppo_a, codice_unita="H2", funzione=FunzioneIncarico.AIUTO_CAPO_UNITA)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert len(righe) == 2
        assert {r.codice_socio for r in righe} == {"10001"}

    def test_capo_a_disposizione_genera_una_riga_sentinella(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert len(righe) == 1
        assert righe[0].funzione == A_DISPOSIZIONE
        assert righe[0].gruppo_servizio_codice == ""

    def test_capo_a_disposizione_ha_unita_e_branca_convenzionali(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert righe[0].nome_unita == "COMUNITA' CAPI"
        assert righe[0].branca == BrancaUnita.ADULTI
        assert etichetta_unita(righe[0].codice_unita, righe[0].nome_unita) == "COMUNITA' CAPI"

    def test_incarico_cessato_non_genera_riga_ma_conta_come_a_disposizione(
        self, gruppo_a, segreteria
    ):
        capo = _capo("10001", gruppo_a)
        incarico = _incarico(capo, gruppo_a)
        incarico.cessato_il = timezone.now()
        incarico.save(update_fields=["cessato_il"])

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert len(righe) == 1
        assert righe[0].funzione == A_DISPOSIZIONE

    def test_entrambe_le_colonne_gruppo_sempre_presenti(self, gruppo_a, gruppo_b, segreteria):
        capo = _capo("10001", gruppo_a)
        _incarico(capo, gruppo_b)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert righe[0].gruppo_censimento_codice == gruppo_a.codice
        assert righe[0].gruppo_servizio_codice == gruppo_b.codice


class TestFiltri:
    def test_filtro_funzione_a_disposizione_isola_i_capi_senza_incarico(self, gruppo_a, segreteria):
        con_incarico = _capo("10001", gruppo_a)
        _incarico(con_incarico, gruppo_a)
        _capo("10002", gruppo_a)

        righe = genera_righe_esportazione(
            segreteria, FiltriEsportazione(anno_scout=ANNO, funzione=(A_DISPOSIZIONE,))
        )

        assert {r.codice_socio for r in righe} == {"10002"}

    def test_filtro_unita(self, gruppo_a, segreteria):
        capo = _capo("10001", gruppo_a)
        _incarico(capo, gruppo_a, codice_unita="H1")
        _incarico(capo, gruppo_a, codice_unita="H2")

        righe = genera_righe_esportazione(
            segreteria, FiltriEsportazione(anno_scout=ANNO, unita=("H1",))
        )

        assert len(righe) == 1
        assert righe[0].codice_unita == "H1"

    def test_filtro_livello_foca_usa_il_valore_del_censimento(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a, livello_foca=1)
        _capo("10002", gruppo_a, livello_foca=2)

        righe = genera_righe_esportazione(
            segreteria, FiltriEsportazione(anno_scout=ANNO, livello_foca=(1,))
        )

        assert {r.codice_socio for r in righe} == {"10001"}

    def test_filtro_stato_attivi_default(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a, attivo=True)
        _capo("10002", gruppo_a, attivo=False)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        assert {r.codice_socio for r in righe} == {"10001"}

    def test_filtro_gruppo_multiplo(self, gruppo_a, gruppo_b, segreteria):
        _capo("10001", gruppo_a)
        _capo("10002", gruppo_b)
        _capo("10003", Gruppo.objects.create(codice="E0135", nome="AVELLINO 3"))

        righe = genera_righe_esportazione(
            segreteria,
            FiltriEsportazione(anno_scout=ANNO, gruppo=(gruppo_a.codice, gruppo_b.codice)),
        )

        assert {r.codice_socio for r in righe} == {"10001", "10002"}

    def test_filtro_livello_foca_multiplo(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a, livello_foca=1)
        _capo("10002", gruppo_a, livello_foca=2)
        _capo("10003", gruppo_a, livello_foca=3)

        righe = genera_righe_esportazione(
            segreteria, FiltriEsportazione(anno_scout=ANNO, livello_foca=(1, 3))
        )

        assert {r.codice_socio for r in righe} == {"10001", "10003"}

    def test_filtro_branca(self, gruppo_a, segreteria):
        capo = _capo("10001", gruppo_a)
        _incarico(capo, gruppo_a, codice_unita="H1")
        IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=gruppo_a,
            codice_unita="R1",
            nome_unita="REPARTO",
            branca=BrancaUnita.EG,
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            origine=OrigineIncarico.IMPORT,
        )

        righe = genera_righe_esportazione(
            segreteria, FiltriEsportazione(anno_scout=ANNO, branca=(BrancaUnita.EG,))
        )

        assert len(righe) == 1
        assert righe[0].codice_unita == "R1"

    def test_filtro_branca_include_i_capi_a_disposizione_su_adulti(self, gruppo_a, segreteria):
        con_incarico = _capo("10001", gruppo_a)
        _incarico(con_incarico, gruppo_a)
        a_disposizione = _capo("10002", gruppo_a)

        righe = genera_righe_esportazione(
            segreteria, FiltriEsportazione(anno_scout=ANNO, branca=(BrancaUnita.ADULTI,))
        )

        assert {r.codice_socio for r in righe} == {a_disposizione.codice_socio}

    def test_filtro_stato_entrambi(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a, attivo=True)
        _capo("10002", gruppo_a, attivo=False)

        righe = genera_righe_esportazione(
            segreteria,
            FiltriEsportazione(anno_scout=ANNO, stato=StatoFiltroEsportazione.ENTRAMBI),
        )

        assert {r.codice_socio for r in righe} == {"10001", "10002"}


class TestColonne:
    def test_profilo_minimo_non_espone_dati_sensibili(self, gruppo_a, segreteria):
        capo = _capo("10001", gruppo_a)
        capo.codice_fiscale = "RSSMRA80A01H501U"
        capo.email = "mario@example.com"
        capo.save(update_fields=["codice_fiscale", "email"])

        colonne = colonne_per_profilo(ProfiloColonneEsportazione.MINIMO)
        etichette = {label for label, _ in colonne}

        assert "Codice fiscale" not in etichette
        assert "Email" not in etichette

    def test_profilo_esteso_espone_i_dati_anagrafici(self):
        colonne = colonne_per_profilo(ProfiloColonneEsportazione.ESTESO)
        etichette = {label for label, _ in colonne}

        assert "Codice fiscale" in etichette
        assert "Email" in etichette


class TestRaggruppamento:
    def test_nessuno_produce_un_unico_gruppo(self, gruppo_a, segreteria):
        _capo("10001", gruppo_a)
        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))

        gruppi = raggruppa_righe(righe, RaggruppamentoEsportazione.NESSUNO)

        assert list(gruppi.keys()) == ["Capi"]

    def test_per_funzione_include_il_foglio_a_disposizione(self, gruppo_a, segreteria):
        capo = _capo("10001", gruppo_a)
        _incarico(capo, gruppo_a)
        _capo("10002", gruppo_a)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))
        gruppi = raggruppa_righe(righe, RaggruppamentoEsportazione.PER_FUNZIONE)

        assert "A disposizione" in gruppi

    def test_per_branca_isola_i_capi_a_disposizione_su_adulti(self, gruppo_a, segreteria):
        capo = _capo("10001", gruppo_a)
        _incarico(capo, gruppo_a)
        _capo("10002", gruppo_a)

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))
        gruppi = raggruppa_righe(righe, RaggruppamentoEsportazione.PER_BRANCA)

        assert set(gruppi.keys()) == {BrancaUnita.LC.label, BrancaUnita.ADULTI.label}
        assert {r.codice_socio for r in gruppi[BrancaUnita.ADULTI.label]} == {"10002"}

    def test_ordina_per_raggruppamento_ordina_senza_dividere(self, gruppo_a, segreteria):
        capo1 = _capo("10001", gruppo_a, cognome="ZETA")
        capo2 = _capo("10002", gruppo_a, cognome="ALPHA")
        _incarico(capo1, gruppo_a, codice_unita="Z1")
        _incarico(capo2, gruppo_a, codice_unita="A1")

        righe = genera_righe_esportazione(segreteria, FiltriEsportazione(anno_scout=ANNO))
        ordinate = ordina_per_raggruppamento(righe, RaggruppamentoEsportazione.PER_UNITA)

        assert [r.codice_unita for r in ordinate] == ["A1", "Z1"]
