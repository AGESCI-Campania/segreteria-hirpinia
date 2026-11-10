from django.urls import path

from . import views, views_urna

app_name = "voto"

urlpatterns = [
    # Pubbliche, senza login.
    path("", views_urna.UrnaView.as_view(), name="urna"),
    path("accedi/", views_urna.AccediView.as_view(), name="accedi"),
    path("scheda/", views_urna.SchedaView.as_view(), name="scheda"),
    path("stato.json", views_urna.StatoView.as_view(), name="stato"),
    path("esci/", views_urna.EsciView.as_view(), name="esci"),
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
