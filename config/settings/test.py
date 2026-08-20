from apps.core.email import backend_path

from .base import *  # noqa: F403

DEBUG = False

# Nessun test deve poter inviare email reali: hardcoded, non dipende da
# EMAIL_PROVIDER d'ambiente.
EMAIL_BACKEND = backend_path("locmem")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
