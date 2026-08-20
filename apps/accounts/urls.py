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
    path("vista-di-prova/", views.VistaDiProvaView.as_view(), name="vista_di_prova"),
]
