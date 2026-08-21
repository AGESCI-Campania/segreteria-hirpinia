from django.http import HttpRequest

from apps.accounts.permessi import puo_impersonare_qualcuno

from .menu import sezioni_menu


def menu_principale(request: HttpRequest) -> dict:
    puo_impersonare = request.user.is_authenticated and puo_impersonare_qualcuno(request.user)
    return {"sezioni_menu": sezioni_menu(request.user), "puo_impersonare": puo_impersonare}
