from django.http import HttpRequest
from django.urls import reverse

from apps.accounts.permessi import puo_impersonare_qualcuno

from .menu import sezioni_menu
from .models import ImpostazioniPiattaforma


def menu_principale(request: HttpRequest) -> dict:
    puo_impersonare = request.user.is_authenticated and puo_impersonare_qualcuno(request.user)
    return {"sezioni_menu": sezioni_menu(request.user), "puo_impersonare": puo_impersonare}


def tema_branca(request: HttpRequest) -> dict:
    """Issue #7: sovrascrive `agesci_theme_branca` (iniettato dal context
    processor del tema, registrato prima di questo in TEMPLATES) con la
    preferenza personale dell'utente loggato o, in assenza, con il default di
    sistema — senza toccare mai l'uno o l'altro fra loro. Nessuna delle due
    query legge `ImpostazioniPiattaforma.corrente()` per non forzare una
    `get_or_create()` scrivente ad ogni richiesta."""
    utente = request.user
    if utente.is_authenticated and utente.branca_tema_preferita:
        return {"agesci_theme_branca": utente.branca_tema_preferita}
    default_sistema = (
        ImpostazioniPiattaforma.objects.filter(pk=1)
        .values_list("branca_tema_default", flat=True)
        .first()
    )
    if default_sistema:
        return {"agesci_theme_branca": default_sistema}
    return {}


def breadcrumb(request: HttpRequest) -> dict:
    """Breadcrumb derivato automaticamente dal menu (`sezioni_menu`): sempre
    presente Home, con Sezione › Voce quando `request.path` corrisponde
    esattamente a una voce di menu. Le pagine "figlie" non presenti nel menu
    (dettaglio, creazione, conferma, ecc.) mostrano solo Home, salvo che la
    view implementi `BreadcrumbExtraMixin` (`apps/core/mixins.py`): in quel
    caso si accodano i suoi item — un'estensione esplicita, non un secondo
    meccanismo che duplica la logica sezione/voce sopra."""
    if not request.user.is_authenticated:
        return {}
    items: list[dict] = [{"label": "Home", "url": reverse("core:home")}]
    for sezione in sezioni_menu(request.user):
        for voce in sezione.voci:
            if voce.url == request.path:
                items.append({"label": sezione.etichetta})
                items.append({"label": voce.etichetta})
                return {"breadcrumb_items": items}

    view_class = getattr(getattr(request.resolver_match, "func", None), "view_class", None)
    breadcrumb_extra = getattr(view_class, "breadcrumb_extra", None)
    if breadcrumb_extra is not None:
        items.extend(breadcrumb_extra(request))
    return {"breadcrumb_items": items}
