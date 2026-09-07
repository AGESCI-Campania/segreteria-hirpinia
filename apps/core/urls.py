from django.conf import settings
from django.urls import path
from django.views.static import serve

from apps.core.views import (
    CaricaImmagineTemplateEmailView,
    HomeView,
    ImpostazioniPiattaformaView,
    PrivacyPolicyView,
    TemplateEmailListaView,
    TemplateEmailModificaView,
)

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    # Uniche fra le FileField del progetto: le immagini della firma email
    # devono essere scaricabili senza sessione Django (client email dei
    # destinatari). Route pubblica non gated da DEBUG, a differenza di
    # MEDIA_URL nel suo complesso (config/urls.py) che in produzione resta
    # senza pattern: import CSV/PDF e allegati restano dietro view
    # autenticate, mai raggiungibili da /media/ direttamente.
    path(
        "media/template_email_immagini/<path:path>",
        serve,
        {"document_root": settings.MEDIA_ROOT / "template_email_immagini"},
        name="template_email_immagine_serve",
    ),
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy"),
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
