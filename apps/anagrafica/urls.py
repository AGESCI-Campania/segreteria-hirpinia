from django.urls import path

from . import views

app_name = "anagrafica"

urlpatterns = [
    path(
        "importazioni/cruscotto/",
        views.ImportazioneCruscottoView.as_view(),
        name="importazione_cruscotto",
    ),
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
    path(
        "importazioni-autorizzazioni/",
        views.ImportazioneAutorizzazioniListaView.as_view(),
        name="importazione_autorizzazioni_lista",
    ),
    path(
        "importazioni-autorizzazioni/nuova/",
        views.ImportazioneAutorizzazioniAnteprimaView.as_view(),
        name="importazione_autorizzazioni_anteprima",
    ),
    path(
        "importazioni-autorizzazioni/conferma/",
        views.ImportazioneAutorizzazioniConfermaView.as_view(),
        name="importazione_autorizzazioni_conferma",
    ),
    path(
        "importazioni-autorizzazioni/<int:pk>/",
        views.ImportazioneAutorizzazioniDettaglioView.as_view(),
        name="importazione_autorizzazioni_dettaglio",
    ),
    path(
        "importazioni-autorizzazioni/<int:pk>/report/",
        views.ImportazioneAutorizzazioniReportCSVView.as_view(),
        name="importazione_autorizzazioni_report",
    ),
    path("incarichi/ricerca-capo/", views.RicercaCapoView.as_view(), name="ricerca_capo"),
    path("incarichi/assegna/", views.AssegnaIncaricoView.as_view(), name="assegna_incarico"),
    path("incarichi/<int:pk>/cessa/", views.CessaIncaricoView.as_view(), name="cessa_incarico"),
    path(
        "capi/<str:codice_socio>/incarichi/",
        views.CapoIncarichiView.as_view(),
        name="capo_incarichi",
    ),
    path("export/", views.EsportazioneAnagraficaView.as_view(), name="esportazione"),
    path(
        "export/registro/",
        views.EsportazioneAnagraficaListaView.as_view(),
        name="esportazione_lista",
    ),
]
