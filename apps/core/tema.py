"""Schemi colore ("branca") selezionabili per la piattaforma (issue #7).

Riusa le palette già pronte in `django-agesci-campania-theme`
(`agesci_theme.context_processors.BRANCHE_VALIDE`), escludendo `viola` perché
alias di `capi` nel tema: evita una scelta duplicata identica in UI.
"""

SCELTE_BRANCA_TEMA = [
    ("generico", "Generico (azzurro)"),
    ("generico2", "Generico 2 (viola indaco)"),
    ("capi", "Capi / Comunità Capi (viola)"),
    ("lc", "Branco/Cerchio (giallo)"),
    ("eg", "Reparto (verde)"),
    ("rs", "Clan/Fuoco (rosso)"),
]
