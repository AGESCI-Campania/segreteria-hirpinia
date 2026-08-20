"""Backend di invio email multi-provider.

La scelta del provider avviene con la variabile d'ambiente ``EMAIL_PROVIDER``, che
``config/settings/base.py`` traduce nel percorso di ``EMAIL_BACKEND``. Tutto il codice
applicativo (incluso allauth) continua a usare ``django.core.mail``: nessuna view e
nessun task deve conoscere il provider attivo.

Provider supportati — vedi § 8 del documento di progettazione:

===========================  ===================================================
``EMAIL_PROVIDER``           Backend
===========================  ===================================================
``console``                  apps.core.email.console.ConsoleFileEmailBackend
``locmem``                   django.core.mail.backends.locmem.EmailBackend
``smtp``                     django.core.mail.backends.smtp.EmailBackend
``gmail_service_account``    apps.core.email.gmail.GmailServiceAccountBackend
``gmail_oauth``              apps.core.email.gmail.GmailOAuthBackend
``microsoft_graph``          apps.core.email.microsoft.MicrosoftGraphBackend
===========================  ===================================================

``console`` è solo di sviluppo: oltre a stampare ogni email sul terminale (come il
backend console standard di Django), la duplica in un file di log — vedi
``apps.core.email.console.ConsoleFileEmailBackend``.
"""

EMAIL_BACKENDS: dict[str, str] = {
    "console": "apps.core.email.console.ConsoleFileEmailBackend",
    "locmem": "django.core.mail.backends.locmem.EmailBackend",
    "smtp": "django.core.mail.backends.smtp.EmailBackend",
    "gmail_service_account": "apps.core.email.gmail.GmailServiceAccountBackend",
    "gmail_oauth": "apps.core.email.gmail.GmailOAuthBackend",
    "microsoft_graph": "apps.core.email.microsoft.MicrosoftGraphBackend",
}

DEFAULT_PROVIDER = "console"


def backend_path(provider: str) -> str:
    """Traduce il nome del provider nel percorso del backend Django.

    Solleva ImproperlyConfigured su un provider sconosciuto: meglio fallire
    all'avvio che scoprire in esercizio che le email non partono.
    """
    from django.core.exceptions import ImproperlyConfigured

    try:
        return EMAIL_BACKENDS[provider]
    except KeyError:
        validi = ", ".join(sorted(EMAIL_BACKENDS))
        raise ImproperlyConfigured(
            f"EMAIL_PROVIDER='{provider}' non riconosciuto. Valori ammessi: {validi}"
        ) from None
