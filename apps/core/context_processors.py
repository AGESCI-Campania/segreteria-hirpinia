from django.http import HttpRequest

from .menu import sezioni_menu


def menu_principale(request: HttpRequest) -> dict:
    sezioni = sezioni_menu(request.user)
    voci_dropdown: list[dict[str, str | bool]] = []
    for indice, sezione in enumerate(sezioni):
        if indice > 0:
            voci_dropdown.append({"divider": True})
        voci_dropdown.extend({"label": v.etichetta, "url": v.url} for v in sezione.voci)
    return {"sezioni_menu": sezioni, "voci_menu_dropdown": voci_dropdown}
