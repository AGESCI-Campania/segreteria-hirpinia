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
        "campagne/<int:pk>/avvia-valutazione/",
        views.CampagnaAvviaValutazioneView.as_view(),
        name="campagna_avvia_valutazione",
    ),
    path(
        "campagne/<int:pk>/simula/",
        views.CampagnaSimulaView.as_view(),
        name="campagna_simula",
    ),
    path(
        "campagne/<int:pk>/chiudi/",
        views.CampagnaChiudiView.as_view(),
        name="campagna_chiudi",
    ),
    path(
        "campagne/<int:pk>/bonifici/",
        views.BonificiGeneraView.as_view(),
        name="campagna_bonifici",
    ),
    path(
        "campagne/<int:pk>/liquida/",
        views.CampagnaLiquidaView.as_view(),
        name="campagna_liquida",
    ),
    path(
        "campagne/<int:pk>/riepilogo.pdf",
        views.CampagnaReportPdfView.as_view(),
        name="campagna_riepilogo_pdf",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/inserisci/",
        views.PartecipazioneInserisciView.as_view(),
        name="partecipazione_inserisci",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/ricerca-soci-autocomplete/",
        views.PartecipazioniRicercaSociAutocompleteView.as_view(),
        name="partecipazioni_ricerca_soci_autocomplete",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/<int:pk>/approva/",
        views.PartecipazioneApprovaView.as_view(),
        name="partecipazione_approva",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/<int:pk>/respingi/",
        views.PartecipazioneRespingiView.as_view(),
        name="partecipazione_respingi",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/<int:pk>/richiedi-documenti/",
        views.PartecipazioneRichiediDocumentiView.as_view(),
        name="partecipazione_richiedi_documenti",
    ),
    path(
        "campagne/<int:campagna_id>/partecipazioni/<int:pk>/allegato/carica/",
        views.AllegatoPartecipazioneCaricaView.as_view(),
        name="partecipazione_allegato_carica",
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
