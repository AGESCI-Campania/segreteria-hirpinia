from django.urls import path

from apps.core.views import (
    CaricaImmagineTemplateEmailView,
    HomeView,
    ImpostazioniPiattaformaView,
    TemplateEmailListaView,
    TemplateEmailModificaView,
)

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("impostazioni/", ImpostazioniPiattaformaView.as_view(), name="impostazioni"),
    path(
        "impostazioni/template-email/",
        TemplateEmailListaView.as_view(),
        name="template_email_lista",
    ),
    path(
        "impostazioni/template-email/<int:pk>/",
        TemplateEmailModificaView.as_view(),
        name="template_email_modifica",
    ),
    path(
        "impostazioni/template-email/carica-immagine/",
        CaricaImmagineTemplateEmailView.as_view(),
        name="template_email_carica_immagine",
    ),
]
