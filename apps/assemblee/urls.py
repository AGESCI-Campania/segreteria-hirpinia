from django.urls import path

from . import views

app_name = "assemblee"

urlpatterns = [
    path("", views.AssembleaListaView.as_view(), name="assemblea_lista"),
    path("nuova/", views.AssembleaCreaView.as_view(), name="assemblea_crea"),
    path("<int:pk>/", views.AssembleaDettaglioView.as_view(), name="assemblea_dettaglio"),
    path("<int:pk>/duplica/", views.AssembleaDuplicaView.as_view(), name="assemblea_duplica"),
    path("<int:pk>/elimina/", views.AssembleaEliminaView.as_view(), name="assemblea_elimina"),
    path("<int:pk>/email-prova/", views.EmailProvaView.as_view(), name="email_prova"),
    path(
        "<int:pk>/comitato/cerca/",
        views.ComitatoAutocompleteView.as_view(),
        name="comitato_cerca",
    ),
    path(
        "<int:pk>/comitato/aggiungi/",
        views.ComitatoAggiungiView.as_view(),
        name="operatore_aggiungi",
    ),
    path(
        "<int:pk>/comitato/<int:operatore_pk>/accesso/",
        views.ComitatoAccessoView.as_view(),
        name="operatore_accesso",
    ),
    path(
        "<int:pk>/incarichi/aggiungi/",
        views.IncaricoAggiungiView.as_view(),
        name="incarico_aggiungi",
    ),
    path(
        "<int:pk>/incarichi/<int:incarico_pk>/accesso/",
        views.IncaricoAccessoView.as_view(),
        name="incarico_accesso",
    ),
    path(
        "<int:pk>/incarichi/<int:incarico_pk>/rimuovi/",
        views.IncaricoRimuoviView.as_view(),
        name="incarico_rimuovi",
    ),
    path(
        "<int:pk>/comitato/<int:operatore_pk>/rimuovi/",
        views.ComitatoRimuoviView.as_view(),
        name="operatore_rimuovi",
    ),
    path("<int:pk>/elenco/", views.ElencoView.as_view(), name="elenco"),
    path("<int:pk>/elenco/riallinea/", views.RiallineaView.as_view(), name="riallinea"),
    path(
        "<int:pk>/elenco/aggiungi/",
        views.AggiungiDaAnagraficaView.as_view(),
        name="aggiungi_anagrafica",
    ),
    path(
        "<int:pk>/elenco/aggiungi/cerca/",
        views.AggiungiDaAnagraficaCercaView.as_view(),
        name="aggiungi_anagrafica_cerca",
    ),
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
    path("<int:pk>/email/", views.EmailAventiView.as_view(), name="email_aventi"),
    path("<int:pk>/email/tutti.zip", views.EmailZipView.as_view(), name="email_zip"),
    path(
        "<int:pk>/email/gruppi/<str:codice>.xlsx",
        views.EmailGruppoView.as_view(),
        name="email_gruppo",
    ),
    path(
        "<int:pk>/email/import/anteprima/",
        views.ImportEmailAnteprimaView.as_view(),
        name="email_import_anteprima",
    ),
    path(
        "<int:pk>/email/import/conferma/",
        views.ImportEmailConfermaView.as_view(),
        name="email_import_conferma",
    ),
    path(
        "<int:pk>/email/import/<int:importazione_pk>/anomalie.csv",
        views.ImportEmailReportView.as_view(),
        name="email_import_report",
    ),
    path(
        "<int:pk>/elenco/<int:avente_pk>/email/",
        views.AventeEmailView.as_view(),
        name="avente_email",
    ),
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
    path(
        "<int:pk>/sedute/<int:seduta_pk>/votazioni/",
        views.VotazioniView.as_view(),
        name="votazioni",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/votazioni/nuova/",
        views.NuovaVotazioneView.as_view(),
        name="votazione_nuova",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/votazioni/<int:votazione_pk>/",
        views.VotazioneView.as_view(),
        name="votazione",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/votazioni/<int:votazione_pk>/azione/",
        views.VotazioneAzioneView.as_view(),
        name="votazione_azione",
    ),
    path("<int:pk>/odg/", views.OdgView.as_view(), name="odg"),
    path("<int:pk>/odg/<int:punto_pk>/", views.PuntoModificaView.as_view(), name="punto"),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/verbale/",
        views.VerbaleView.as_view(),
        name="verbale",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/verbale/pdf/",
        views.VerbalePdfView.as_view(),
        name="verbale_pdf",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/verbale/rappresentante-legale/",
        views.VariazioneRappresentanteView.as_view(),
        name="variazione_rappresentante",
    ),
    path(
        "<int:pk>/sedute/<int:seduta_pk>/verbale/rappresentante-legale/pdf/",
        views.VariazioneRappresentantePdfView.as_view(),
        name="variazione_rappresentante_pdf",
    ),
]
