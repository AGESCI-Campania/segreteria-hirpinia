from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import BASE_DIR, EMAIL_PROVIDER, _env_bool

DEBUG = False

# D-17/§8 (docs/email/README.md): console e locmem sono provider di sviluppo/test,
# mai di produzione. Bloccarlo qui evita che un .env dimenticato faccia
# silenziosamente cadere le email di produzione nel file log/email-console.log
# invece di essere consegnate davvero (vedi docs/docker.md § Log).
if EMAIL_PROVIDER in {"console", "locmem"}:
    raise ImproperlyConfigured(
        f"EMAIL_PROVIDER={EMAIL_PROVIDER!r} non è ammesso in produzione "
        "(config.settings.prod): usa smtp, gmail_service_account, gmail_oauth "
        "o microsoft_graph."
    )

# Tabella creata una tantum con `manage.py createcachetable` (comando NON
# idempotente: non va in docker/entrypoint.sh, va eseguito manualmente al primo
# deploy — vedi README §Produzione).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache_table",
    }
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Disattivati di default: vanno attivati solo a valle di un vero reverse proxy
# TLS (generato da configure-prod.sh). Di default romperebbero la verifica
# diretta su HTTP in fase di scaffold/primo deploy.
SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = _env_bool("DJANGO_SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = _env_bool("DJANGO_CSRF_COOKIE_SECURE", default=False)

LOG_DIR = BASE_DIR / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "catello.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
