import pytest

from apps.organizzazione.models import Gruppo, StatoGruppoAnno

pytestmark = pytest.mark.django_db


@pytest.fixture
def gruppo():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


def _confronta_attivo_istanza_e_queryset(gruppo, anno):
    da_istanza = gruppo.e_attivo(anno)
    da_queryset = Gruppo.objects.attivi(anno).filter(codice=gruppo.codice).exists()
    assert da_istanza == da_queryset
    return da_istanza


class TestGruppoEAttivo:
    def test_attivo_di_default_senza_stato_gruppo_anno(self, gruppo):
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2026) is True

    def test_disattivazione_esplicita(self, gruppo):
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=False)
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2026) is False

    def test_disattivazione_non_influisce_su_anno_precedente(self, gruppo):
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=False)
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2025) is True

    def test_disattivazione_si_propaga_agli_anni_successivi(self, gruppo):
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=False)
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2027) is False

    def test_riattivazione_successiva(self, gruppo):
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=False)
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2028, attivo=True)
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2027) is False
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2028) is True

    def test_risoluzione_anno_piu_alto_fra_quelli_minori_o_uguali(self, gruppo):
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2024, attivo=False)
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=True)
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2030, attivo=False)
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2027) is True
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2029) is True
        assert _confronta_attivo_istanza_e_queryset(gruppo, 2031) is False


class TestAccountConsentiti:
    def test_default_uno(self, gruppo):
        assert gruppo.account_consentiti == 1

    def test_override_per_e9001(self):
        # E9001 è seminato dalla data migration 0002_seed_e9001 (D-33).
        e9001 = Gruppo.objects.get(codice="E9001")
        assert e9001.account_consentiti == 2
        assert e9001.is_comitato_zona is True
