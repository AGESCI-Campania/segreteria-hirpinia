from django.urls import path

from . import views

app_name = "voto"

urlpatterns = [
    # Pubbliche, senza login.
    path("", views.UrnaView.as_view(), name="urna"),
    # Banco e gestione (login): stessa struttura di URL delle assemblee.
    path(
        "gestione/<int:pk>/sistema/",
        views.SistemaVotoView.as_view(),
        name="sistema",
    ),
    path(
        "gestione/<int:pk>/sedute/<int:seduta_pk>/codici/<int:avente_pk>/invia/",
        views.CodiceInviaView.as_view(),
        name="codice_invia",
    ),
    path(
        "gestione/<int:pk>/sedute/<int:seduta_pk>/codici/<int:avente_pk>/mostra/",
        views.CodiceMostraView.as_view(),
        name="codice_mostra",
    ),
]
