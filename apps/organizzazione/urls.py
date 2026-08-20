from django.urls import path

from . import views

app_name = "organizzazione"

urlpatterns = [
    path("", views.GruppoListaView.as_view(), name="gruppo_lista"),
    path("nuovo/", views.GruppoCreaView.as_view(), name="gruppo_crea"),
    path("<str:codice>/disattiva/", views.GruppoDisattivaView.as_view(), name="gruppo_disattiva"),
    path("<str:codice>/riattiva/", views.GruppoRiattivaView.as_view(), name="gruppo_riattiva"),
]
