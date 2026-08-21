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
