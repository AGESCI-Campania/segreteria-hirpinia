"""Backend di invio email multi-provider.

La scelta del provider avviene con la variabile d'ambiente ``EMAIL_PROVIDER``, che
``config/settings/base.py`` traduce nel mailer ``default`` di ``MAILERS`` (Django 6.1)
con ``configurazione_mailer()``. Tutto il codice
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

#: OPTIONS che ciascun backend accetta. Con MAILERS Django rifiuta all'avvio della
#: connessione (InvalidMailer) ogni opzione sconosciuta al backend: a ogni provider
#: si passa quindi solo ciò che usa davvero. ``microsoft_graph`` resta vuoto finché
#: il suo backend non esiste nel repository.
OPZIONI_ACCETTATE: dict[str, tuple[str, ...]] = {
    "console": (),
    "locmem": (),
    "smtp": ("host", "port", "username", "password", "use_tls", "use_ssl", "timeout"),
    "gmail_service_account": ("timeout",),
    "gmail_oauth": ("timeout",),
    "microsoft_graph": (),
}


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


def configurazione_mailer(provider: str, opzioni: dict[str, object]) -> dict[str, object]:
    """Voce di ``MAILERS`` per il provider: ``BACKEND`` più le sole ``OPTIONS``
    che quel backend accetta (vedi ``OPZIONI_ACCETTATE``).

    ``opzioni`` arriva da ``config/settings/base.py``, già letto dalle variabili
    d'ambiente ``EMAIL_HOST``, ``EMAIL_PORT``… (nomi invariati per i ``.env``
    esistenti): con MAILERS definito Django vieta le omonime impostazioni
    ``EMAIL_*``, che quindi non esistono più come settings.
    """
    backend = backend_path(provider)
    accettate = OPZIONI_ACCETTATE[provider]
    return {
        "BACKEND": backend,
        "OPTIONS": {nome: valore for nome, valore in opzioni.items() if nome in accettate},
    }
