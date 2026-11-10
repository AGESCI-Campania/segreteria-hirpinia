from apps.core.email import configurazione_mailer

from .base import *  # noqa: F403

DEBUG = False

# Nessun test deve poter inviare email reali: hardcoded, non dipende da
# EMAIL_PROVIDER d'ambiente.
# (setup_test_environment di Django sostituisce comunque ogni alias di MAILERS
# con locmem: qui è esplicito anche per chi importa i settings fuori dai test.)
MAILERS = {"default": configurazione_mailer("locmem", {})}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Come MAILERS sopra: i test non devono dipendere da un .env locale,
# altrimenti passano solo su chi ce l'ha configurato e falliscono in CI
# (dove DOMINI_RUOLI_EFFETTIVI non è impostata). Hardcoded, non letto
# dall'ambiente.
DOMINI_RUOLI_EFFETTIVI = ["campania.agesci.it", "zonahirpinia.org"]
