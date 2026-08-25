"""Estensione del breadcrumb per pagine "figlie" non presenti nel menu (es.
`gruppo_gestione/<codice>/`): `apps.core.context_processors.breadcrumb` legge
`breadcrumb_extra` da `request.resolver_match.func.view_class` quando il path
non combacia con nessuna voce di `sezioni_menu`. Non tocca il comportamento
delle altre pagine: senza questo mixin il breadcrumb resta invariato."""

from __future__ import annotations

from django.http import HttpRequest


class BreadcrumbExtraMixin:
    """Una vista che eredita da questo mixin implementa `breadcrumb_extra()`
    (classmethod, riceve la `request` per leggere `resolver_match.kwargs`)
    restituendo gli item da accodare dopo "Home" — mai un rimpiazzo completo,
    solo un'estensione."""

    @classmethod
    def breadcrumb_extra(cls, request: HttpRequest) -> list[dict]:
        raise NotImplementedError
