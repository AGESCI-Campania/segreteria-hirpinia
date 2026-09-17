from django.urls import path

from . import views

app_name = "note_spese"

urlpatterns = [
    path("", views.NotaListaView.as_view(), name="nota_lista"),
    path("<int:pk>/", views.NotaDettaglioView.as_view(), name="nota_dettaglio"),
    path(
        "allegati/<int:pk>/scarica/", views.AllegatoScaricaView.as_view(), name="allegato_scarica"
    ),
]
