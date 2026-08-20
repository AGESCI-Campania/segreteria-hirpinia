"""Settings condivisi da dev, test e prod.

Ogni valore che dipende dall'ambiente si legge da variabile d'ambiente qui, una sola
volta: dev/test/prod differiscono solo per i *valori* (locali in ``.env``, iniettati da
CI, o passati dal container), non per la struttura.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from apps.core.email import DEFAULT_PROVIDER, backend_path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def _env_list(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "catello"),
        "USER": os.environ.get("POSTGRES_USER", "catello"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terze parti — solo quelle che non richiedono configurazione funzionale
    # prematura (M1+). django-allauth e django-fsm-2 sono deliberatamente
    # esclusi: vedi CLAUDE.md / piano M0 per la motivazione.
    "agesci_theme",
    "auditlog",
    "guardian",
    "hijack",
    "axes",
    # App locali
    "apps.core",
    "apps.anagrafica",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "agesci_theme.context_processors.agesci_theme",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

# ─── Email (§ 8 del documento di progettazione) ────────────────────────────────
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", DEFAULT_PROVIDER)
EMAIL_BACKEND = backend_path(EMAIL_PROVIDER)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")

if _env_bool("EMAIL_USE_TLS") and _env_bool("EMAIL_USE_SSL"):
    raise ImproperlyConfigured("EMAIL_USE_TLS e EMAIL_USE_SSL non possono essere entrambi attivi.")

EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "20"))

# ─── Parametri applicativi, usati a partire da M1+ ─────────────────────────────
DOMINI_RUOLI_EFFETTIVI = _env_list("DOMINI_RUOLI_EFFETTIVI")
EMAIL_SEGRETERIA = os.environ.get("EMAIL_SEGRETERIA", "")
CAUSALE_BONIFICO_DEFAULT = os.environ.get(
    "CAUSALE_BONIFICO_DEFAULT", "Contributo FoCa {anno} - AGESCI Zona Hirpinia"
)

# ─── Tema (D-15) ────────────────────────────────────────────────────────────────
AGESCI_THEME_BRANCA = "capi"
AGESCI_THEME_NOME = "Zona Hirpinia"
AGESCI_THEME_LOGO_NAVBAR = "agesci_theme/img/zone/CAMPANIA_HIRPINIA.png"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
