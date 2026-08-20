import os

from .base import *  # noqa: F403
from .base import BASE_DIR, MIDDLEWARE, _env_bool

DEBUG = _env_bool("DEBUG", default=True)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Usato dal provider EMAIL_PROVIDER=console (apps.core.email.console): oltre a
# stampare le email sul terminale, le duplica su file per poterle rileggere anche
# fuori dal terminale di `runserver`.
EMAIL_CONSOLE_LOG_FILE = Path(  # noqa: F405
    os.environ.get("EMAIL_CONSOLE_LOG_FILE", str(BASE_DIR / "log" / "email-console.log"))
)
EMAIL_CONSOLE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]  # noqa: F405

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE[1:],
]

INTERNAL_IPS = ["127.0.0.1"]
