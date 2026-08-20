"""Configurazione ASGI per Catello.

Non usato in v1 (nessun consumer async previsto, D-17: niente Celery/broker).
Presente per completezza. Stesso default prudente di ``wsgi.py``.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
