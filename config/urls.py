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
    # Solo sviluppo: in produzione /media/ è servito dal reverse proxy
    # (configure-prod.sh), mai da Django/gunicorn.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
