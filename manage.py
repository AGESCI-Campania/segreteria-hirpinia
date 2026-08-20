#!/usr/bin/env python
"""Utility a riga di comando di Django."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Impossibile importare Django. È attivato l'ambiente virtuale? "
            "Prova con 'uv sync' e poi 'uv run python manage.py ...'."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
