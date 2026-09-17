from django.urls import path

from . import views

app_name = "note_spese"

urlpatterns = [
    path("", views.NotaListaView.as_view(), name="nota_lista"),
    path("nuova/", views.NotaCreaView.as_view(), name="nota_crea"),
    path("eventi/nuovo/", views.EventoCreaView.as_view(), name="evento_crea"),
    path("<int:pk>/", views.NotaDettaglioView.as_view(), name="nota_dettaglio"),
    path("<int:pk>/righe/aggiungi/", views.RigaCreaView.as_view(), name="riga_crea"),
    path("<int:pk>/righe/aggiungi-auto/", views.RigaAutoCreaView.as_view(), name="riga_auto_crea"),
    path(
        "<int:nota_pk>/righe/<int:riga_pk>/duplica/",
        views.RigaDuplicaView.as_view(),
        name="riga_duplica",
    ),
    path(
        "<int:nota_pk>/righe/<int:riga_pk>/allegati/carica/",
        views.AllegatoCaricaView.as_view(),
        name="allegato_carica",
    ),
    path(
        "allegati/<int:pk>/scarica/", views.AllegatoScaricaView.as_view(), name="allegato_scarica"
    ),
    path(
        "localita/ricerca-autocomplete/",
        views.LocalitaRicercaAutocompleteView.as_view(),
        name="localita_ricerca_autocomplete",
    ),
]
