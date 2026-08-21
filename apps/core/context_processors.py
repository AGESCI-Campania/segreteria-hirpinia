from django.http import HttpRequest

from .menu import sezioni_menu


def menu_principale(request: HttpRequest) -> dict:
    return {"sezioni_menu": sezioni_menu(request.user)}
