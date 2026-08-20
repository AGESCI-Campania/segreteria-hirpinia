from django.urls import path

from . import views

app_name = "contributi"

urlpatterns = [
    path("campagne/", views.CampagnaListaView.as_view(), name="campagna_lista"),
    path("campagne/nuova/", views.CampagnaCreaView.as_view(), name="campagna_crea"),
    path(
        "campagne/<int:pk>/",
        views.CampagnaDettaglioView.as_view(),
        name="campagna_dettaglio",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/inserisci/",
        views.PartecipazioneInserisciView.as_view(),
        name="partecipazione_inserisci",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/importa/",
        views.PartecipazioniImportAnteprimaView.as_view(),
        name="partecipazioni_import_anteprima",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/importa/conferma/",
        views.PartecipazioniImportConfermaView.as_view(),
        name="partecipazioni_import_conferma",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/modello.xlsx",
        views.ModelloXlsxPartecipazioniView.as_view(),
        name="partecipazioni_modello_xlsx",
    ),
    path(
        "importazioni-partecipazioni/<int:pk>/",
        views.ImportazionePartecipazioniDettaglioView.as_view(),
        name="importazione_partecipazioni_dettaglio",
    ),
]
