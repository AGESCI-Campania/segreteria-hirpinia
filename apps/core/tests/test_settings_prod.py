"""Test della guardia in `config/settings/prod.py` che blocca `EMAIL_PROVIDER`
console/locmem in produzione. Il controllo scatta all'*import* del modulo
settings: la fixture `settings` di pytest-django patcha settings già caricati
e non intercetterebbe un `ImproperlyConfigured` sollevato durante l'import,
per questo qui si usa un sottoprocesso che importa `config.settings.prod` a
freddo con un ambiente controllato."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[3]


def _importa_prod_settings(**env_override) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "SECRET_KEY": "chiave-di-test",
        **env_override,
    }
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        env=env,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )


@pytest.mark.parametrize("provider", ["console", "locmem"])
def test_provider_dev_bloccato_in_produzione(provider):
    risultato = _importa_prod_settings(EMAIL_PROVIDER=provider)

    assert risultato.returncode != 0
    assert "EMAIL_PROVIDER" in risultato.stderr
    assert "ImproperlyConfigured" in risultato.stderr


def test_provider_smtp_non_bloccato_in_produzione():
    risultato = _importa_prod_settings(EMAIL_PROVIDER="smtp")

    assert risultato.returncode == 0, risultato.stderr


def test_admins_vuoto_senza_env():
    risultato = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.settings.prod; print(config.settings.prod.ADMINS)",
        ],
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "SECRET_KEY": "chiave-di-test",
            "EMAIL_PROVIDER": "smtp",
        },
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )
    assert risultato.returncode == 0, risultato.stderr
    assert risultato.stdout.strip() == "[]"


def test_admins_popolato_da_env():
    risultato = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.settings.prod; print(config.settings.prod.ADMINS)",
        ],
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "SECRET_KEY": "chiave-di-test",
            "EMAIL_PROVIDER": "smtp",
            "DJANGO_ADMINS": "Segreteria:segreteria@example.org,Admin:admin@example.org",
        },
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )
    assert risultato.returncode == 0, risultato.stderr
    assert risultato.stdout.strip() == (
        "[('Segreteria', 'segreteria@example.org'), ('Admin', 'admin@example.org')]"
    )


def test_logging_ha_mail_admins_su_django_request():
    risultato = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.settings.prod as s\n"
            "assert 'mail_admins' in s.LOGGING['handlers']\n"
            "assert 'mail_admins' in s.LOGGING['loggers']['django.request']['handlers']\n"
            "print('ok')",
        ],
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "SECRET_KEY": "chiave-di-test",
            "EMAIL_PROVIDER": "smtp",
        },
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )
    assert risultato.returncode == 0, risultato.stderr
    assert risultato.stdout.strip() == "ok"


def test_mailers_default_e_override_mailpit():
    # M-mailpit: in produzione il mailer "default" è sempre il backend che
    # decide a ogni invio (via ImpostazioniPiattaforma), non il provider
    # scelto direttamente — vedi apps/core/email/override.py. Il provider di
    # EMAIL_PROVIDER resta raggiungibile come alias "provider".
    risultato = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.settings.prod as s; "
            "print(s.MAILERS['default']['BACKEND']); "
            "print(s.MAILERS['provider']['BACKEND']); "
            "print(s.MAILERS['mailpit']['BACKEND'])",
        ],
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "SECRET_KEY": "chiave-di-test",
            "EMAIL_PROVIDER": "smtp",
        },
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )

    assert risultato.returncode == 0, risultato.stderr
    assert risultato.stdout.split() == [
        "apps.core.email.override.MailpitOverridableBackend",
        "django.core.mail.backends.smtp.EmailBackend",
        "django.core.mail.backends.smtp.EmailBackend",
    ]


def test_prod_si_avvia_con_mailers_senza_impostazioni_email_deprecate():
    # Con MAILERS definito Django rifiuta all'avvio EMAIL_HOST/EMAIL_TIMEOUT/…
    # (ImproperlyConfigured): django.setup() deve riuscire senza errori.
    risultato = subprocess.run(
        [sys.executable, "-c", "import django; django.setup(); print('ok')"],
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "SECRET_KEY": "chiave-di-test",
            "EMAIL_PROVIDER": "smtp",
        },
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )

    assert risultato.returncode == 0, risultato.stderr
    assert risultato.stdout.strip() == "ok"
