from django.urls import path

from . import views

app_name = "note_spese"

urlpatterns = [
    path("", views.NotaListaView.as_view(), name="nota_lista"),
    path("verifica/", views.NotaVerificaListaView.as_view(), name="nota_verifica_lista"),
    path("nuova/", views.NotaCreaView.as_view(), name="nota_crea"),
    path("eventi/nuovo/", views.EventoCreaView.as_view(), name="evento_crea"),
    path("eventi/", views.EventoListaView.as_view(), name="evento_lista"),
    path("eventi/<int:pk>/valida/", views.EventoValidaView.as_view(), name="evento_valida"),
    path("eventi/<int:pk>/modifica/", views.EventoModificaView.as_view(), name="evento_modifica"),
    path("eventi/<int:pk>/fondi/", views.EventoFondiView.as_view(), name="evento_fondi"),
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
    # F6d — transizioni di stato
    path("<int:pk>/invia/", views.NotaInviaView.as_view(), name="nota_invia"),
    path(
        "<int:pk>/prendi-in-carico/",
        views.NotaPrendiInCaricoView.as_view(),
        name="nota_prendi_in_carico",
    ),
    path(
        "<int:pk>/richiedi-integrazione/",
        views.NotaRichiediIntegrazioneView.as_view(),
        name="nota_richiedi_integrazione",
    ),
    path(
        "<int:pk>/richiedi-conferma/",
        views.NotaRichiediConfermaView.as_view(),
        name="nota_richiedi_conferma",
    ),
    path(
        "<int:pk>/conferma-integrazione/",
        views.NotaConfermaIntegrazioneView.as_view(),
        name="nota_conferma_integrazione",
    ),
    path(
        "<int:pk>/conferma-correzione/",
        views.NotaConfermaCorrezioneView.as_view(),
        name="nota_conferma_correzione",
    ),
    path("<int:pk>/approva/", views.NotaApprovaView.as_view(), name="nota_approva"),
    path(
        "<int:pk>/autorizza-rdz/", views.NotaAutorizzaRdzView.as_view(), name="nota_autorizza_rdz"
    ),
    path("<int:pk>/liquida/", views.NotaLiquidaView.as_view(), name="nota_liquida"),
    path("<int:pk>/respingi/", views.NotaRespingiView.as_view(), name="nota_respingi"),
    path("<int:pk>/annulla/", views.NotaAnnullaView.as_view(), name="nota_annulla"),
]
