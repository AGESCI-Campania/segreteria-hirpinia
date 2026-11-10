from django.urls import path

from . import views

app_name = "assemblee"

urlpatterns = [
    path("", views.AssembleaListaView.as_view(), name="assemblea_lista"),
    path("nuova/", views.AssembleaCreaView.as_view(), name="assemblea_crea"),
    path("<int:pk>/", views.AssembleaDettaglioView.as_view(), name="assemblea_dettaglio"),
    path(
        "<int:pk>/operatori/aggiungi/",
        views.OperatoreAggiungiView.as_view(),
        name="operatore_aggiungi",
    ),
    path(
        "<int:pk>/operatori/<int:operatore_pk>/rimuovi/",
        views.OperatoreRimuoviView.as_view(),
        name="operatore_rimuovi",
    ),
]
