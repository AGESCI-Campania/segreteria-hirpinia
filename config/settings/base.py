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

AUTH_USER_MODEL = "accounts.Utente"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terze parti
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "agesci_theme",
    "auditlog",
    "guardian",
    "hijack",
    "axes",
    # App locali
    "apps.core",
    "apps.organizzazione",
    "apps.accounts",
    "apps.anagrafica",
    "apps.contributi",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.accounts.middleware.MFAEnforcementMiddleware",
    "apps.accounts.middleware.StatoUtenteMiddleware",
    "apps.accounts.audit.CatelloAuditlogMiddleware",
    "hijack.middleware.HijackUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
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

# ─── Autenticazione (D-05, D-20, D-26, D-27) ───────────────────────────────────
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_ADAPTER = "apps.accounts.adapters.CatelloAccountAdapter"
ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"

MFA_ADAPTER = "apps.accounts.adapters.CatelloMFAAdapter"
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # ore
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_COOL_OFF_ON_FAILURE = False

HIJACK_PERMISSION_CHECK = "apps.accounts.permessi.puo_impersonare"
HIJACK_LOGIN_REDIRECT_URL = "/"
HIJACK_LOGOUT_REDIRECT_URL = "/"
HIJACK_INSERT_BEFORE = "</body>"

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

# D-05 impone la MFA per ADMIN/SEGRETERIA; D-20 la estende esplicitamente a RDZ
# all'attivazione dell'account: non e' una deviazione, e' la sintesi delle due
# decisioni.
RUOLI_MFA_OBBLIGATORIA = {"ADMIN", "SEGRETERIA", "RDZ"}

# D-26: numero massimo di deleghe attive per uno stesso ruolo.
MAX_DELEGHE_ATTIVE_PER_RUOLO = 3

# Usato per costruire link assoluti nelle email (attivazione, recupero OTP):
# niente framework Sites, un solo valore letto dall'ambiente.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

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
