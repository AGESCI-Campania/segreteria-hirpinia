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
    path("<int:pk>/elenco/", views.ElencoView.as_view(), name="elenco"),
    path("<int:pk>/elenco/elimina/", views.EliminaView.as_view(), name="elimina"),
    path("<int:pk>/elenco/nuovo/", views.InserisciView.as_view(), name="inserisci"),
    path(
        "<int:pk>/elenco/<int:avente_pk>/ripristina/",
        views.RipristinaView.as_view(),
        name="ripristina",
    ),
    path(
        "<int:pk>/elenco/<int:avente_pk>/trasferisci/",
        views.TrasferisciView.as_view(),
        name="trasferisci",
    ),
    path(
        "<int:pk>/elenco/<int:avente_pk>/voto-cartaceo/",
        views.PassaACartaView.as_view(),
        name="passa_a_carta",
    ),
    path(
        "<int:pk>/elenco/gruppi/<str:codice>/aggiorna/",
        views.AggiornaGruppoView.as_view(),
        name="aggiorna_gruppo",
    ),
]
