"""SCELTE_BRANCA_TEMA deve restare un sottoinsieme delle branche valide del
tema: previene un disallineamento silenzioso a un aggiornamento futuro di
`django-agesci-campania-theme` (issue #7)."""

from agesci_theme.context_processors import BRANCHE_VALIDE

from apps.core.tema import SCELTE_BRANCA_TEMA


def test_valori_sono_tutti_branche_valide_del_tema():
    valori = {valore for valore, _ in SCELTE_BRANCA_TEMA}
    assert valori <= BRANCHE_VALIDE


def test_nessun_valore_duplicato():
    valori = [valore for valore, _ in SCELTE_BRANCA_TEMA]
    assert len(valori) == len(set(valori))
