"""Albero delle categorie di spesa (D-46): unico punto che risale da una
categoria a qualunque profondità al suo nodo di primo livello ("categoria
principale"), usato sia da `esportazione.py` (D-68, colonne dinamiche del
riepilogo di bilancio) sia da `pdf.py` (D-67, totali per categoria
principale nel PDF della nota) — D-69, nessuna duplicazione della regola."""

from __future__ import annotations

from .models import CategoriaSpesa


def mappa_categoria_principale() -> dict[int, CategoriaSpesa]:
    """Per ogni categoria (a qualunque profondità), il suo nodo di primo
    livello: una sola query su tutto l'albero, poi solo lookup in memoria —
    non una query per riga quando si itera su molte righe di spesa."""
    tutte = {c.pk: c for c in CategoriaSpesa.objects.all()}
    mappa: dict[int, CategoriaSpesa] = {}
    for pk, categoria in tutte.items():
        nodo = categoria
        while nodo.parent_id is not None:
            nodo = tutte[nodo.parent_id]
        mappa[pk] = nodo
    return mappa
