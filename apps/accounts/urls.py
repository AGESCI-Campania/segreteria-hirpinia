from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("attesa/", views.AttesaView.as_view(), name="attesa"),
    path("gruppo-non-attivo/", views.GruppoNonAttivoView.as_view(), name="gruppo_non_attivo"),
    path("attiva/", views.AttivazioneView.as_view(), name="attiva"),
    path("recupero/", views.RecuperoOtpView.as_view(), name="recupero"),
    path("inviti/", views.InvitoListaView.as_view(), name="invito_lista"),
    path("inviti/nuovo/", views.InvitoCreaView.as_view(), name="invito_crea"),
    path("deleghe/", views.DelegheListaView.as_view(), name="deleghe_lista"),
    path("deleghe/nuova/", views.DelegaCreaView.as_view(), name="delega_crea"),
    path("deleghe/<int:pk>/revoca/", views.DelegaRevocaView.as_view(), name="delega_revoca"),
    path("deleghe/zona/", views.DelegheZonaListaView.as_view(), name="deleghe_zona"),
    path("ruoli/", views.RuoloListaView.as_view(), name="ruolo_lista"),
    path("ruoli/<int:pk>/revoca/", views.RuoloRevocaView.as_view(), name="ruolo_revoca"),
    path(
        "ruoli/assegna/",
        views.RuoloAssegnaCercaView.as_view(),
        name="ruolo_assegna_cerca",
    ),
    path("ruoli/assegna/nuovo/", views.RuoloAssegnaView.as_view(), name="ruolo_assegna"),
    path("vista-di-prova/", views.VistaDiProvaView.as_view(), name="vista_di_prova"),
    path("impersona/", views.ImpersonaListaView.as_view(), name="impersona_lista"),
]
