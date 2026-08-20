from django.urls import path

from apps.core.views import HomeView, ImpostazioniPiattaformaView

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("impostazioni/", ImpostazioniPiattaformaView.as_view(), name="impostazioni"),
]
