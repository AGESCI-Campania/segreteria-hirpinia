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
    path("<int:pk>/file/tracciato-app/", views.TracciatoView.as_view(), name="tracciato"),
    path(
        "<int:pk>/file/foglio-presenze/",
        views.FoglioPresenzeView.as_view(),
        name="foglio_presenze",
    ),
    path(
        "<int:pk>/convocazioni/nuova/",
        views.NuovaConvocazioneView.as_view(),
        name="convocazione_nuova",
    ),
    path("<int:pk>/sedute/<int:seduta_pk>/", views.SedutaView.as_view(), name="seduta"),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/azione/",
        views.SedutaAzioneView.as_view(),
        name="seduta_azione",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/presenze/",
        views.PresenzeView.as_view(),
        name="presenze",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/presenze/<int:avente_pk>/",
        views.PresenzaView.as_view(),
        name="presenza",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/deleghe/",
        views.DelegheView.as_view(),
        name="deleghe",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/deleghe/<int:delega_pk>/revoca/",
        views.DelegaRevocaView.as_view(),
        name="delega_revoca",
    ),
    path(
        "<int:pk>/elenco/<int:avente_pk>/qualifiche/",
        views.QualificheView.as_view(),
        name="qualifiche",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/stato.json",
        views.StatoSedutaView.as_view(),
        name="stato_seduta",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/cruscotto/",
        views.CruscottoView.as_view(),
        name="cruscotto",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/proiettore/",
        views.ProiettoreView.as_view(),
        name="proiettore",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/abilitazione-app/",
        views.AbilitazioneAppView.as_view(),
        name="abilitazione_app",
    ),
]
