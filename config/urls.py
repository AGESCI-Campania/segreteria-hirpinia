from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("anagrafica/", include("apps.anagrafica.urls")),
    path("contributi/", include("apps.contributi.urls")),
    path("gruppi/", include("apps.organizzazione.urls")),
    path("hijack/", include("hijack.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf.urls.static import static

    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    # Solo sviluppo: serve tutto MEDIA_ROOT senza autenticazione, comodo in
    # locale ma non accettabile in produzione (PDF/CSV con dati personali).
    # In produzione l'unico sottoalbero pubblico (immagini firma email) ha
    # una route dedicata in apps/core/urls.py, non gated da DEBUG; il resto
    # di /media/ resta senza pattern e richiede le view autenticate.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
