from django.urls import path

from . import views

app_name = "organizzazione"

urlpatterns = [
    path("", views.GruppoListaView.as_view(), name="gruppo_lista"),
    path("nuovo/", views.GruppoCreaView.as_view(), name="gruppo_crea"),
    path("<str:codice>/disattiva/", views.GruppoDisattivaView.as_view(), name="gruppo_disattiva"),
    path("<str:codice>/riattiva/", views.GruppoRiattivaView.as_view(), name="gruppo_riattiva"),
    path("allowlist/", views.AllowlistListaView.as_view(), name="allowlist_lista"),
    path("allowlist/nuova/", views.AllowlistCreaView.as_view(), name="allowlist_crea"),
    path(
        "allowlist/invita/",
        views.AllowlistInvitoMassivoView.as_view(),
        name="allowlist_invita_massivo",
    ),
    path(
        "allowlist/<int:pk>/elimina/",
        views.AllowlistEliminaView.as_view(),
        name="allowlist_elimina",
    ),
]
