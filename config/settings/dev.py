from .base import *  # noqa: F403
from .base import MIDDLEWARE, _env_bool

DEBUG = _env_bool("DEBUG", default=True)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]  # noqa: F405

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE[1:],
]

INTERNAL_IPS = ["127.0.0.1"]
