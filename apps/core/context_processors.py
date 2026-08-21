from django.http import HttpRequest
from django.urls import reverse

from apps.accounts.permessi import puo_impersonare_qualcuno

from .menu import sezioni_menu


def menu_principale(request: HttpRequest) -> dict:
    puo_impersonare = request.user.is_authenticated and puo_impersonare_qualcuno(request.user)
    return {"sezioni_menu": sezioni_menu(request.user), "puo_impersonare": puo_impersonare}


def breadcrumb(request: HttpRequest) -> dict:
    """Breadcrumb derivato automaticamente dal menu (`sezioni_menu`): sempre
    presente Home, con Sezione › Voce quando `request.path` corrisponde
    esattamente a una voce di menu. Le pagine "figlie" non presenti nel menu
    (dettaglio, creazione, conferma, ecc.) mostrano solo Home — soddisfa il
    requisito minimo del TODO senza duplicare il trail in ogni view."""
    if not request.user.is_authenticated:
        return {}
    items: list[dict] = [{"label": "Home", "url": reverse("core:home")}]
    for sezione in sezioni_menu(request.user):
        for voce in sezione.voci:
            if voce.url == request.path:
                items.append({"label": sezione.etichetta})
                items.append({"label": voce.etichetta})
                return {"breadcrumb_items": items}
    return {"breadcrumb_items": items}
