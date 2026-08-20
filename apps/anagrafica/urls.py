from django.urls import path

from . import views

app_name = "anagrafica"

urlpatterns = [
    path(
        "importazioni/",
        views.ImportazioneListaView.as_view(),
        name="importazione_lista",
    ),
    path(
        "importazioni/nuova/",
        views.ImportazioneAnteprimaView.as_view(),
        name="importazione_anteprima",
    ),
    path(
        "importazioni/conferma/",
        views.ImportazioneConfermaView.as_view(),
        name="importazione_conferma",
    ),
    path(
        "importazioni/<int:pk>/",
        views.ImportazioneDettaglioView.as_view(),
        name="importazione_dettaglio",
    ),
    path(
        "importazioni/<int:pk>/report/",
        views.ImportazioneReportCSVView.as_view(),
        name="importazione_report",
    ),
]
