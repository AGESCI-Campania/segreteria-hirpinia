"""Configurazione WSGI per Catello.

Entrypoint di produzione (``gunicorn config.wsgi:application``). Il default è
deliberatamente ``config.settings.prod``, non ``dev``: ``compose.prod.yaml`` imposta
sempre esplicitamente ``DJANGO_SETTINGS_MODULE``, ma se per errore il server venisse
avviato senza quella variabile è più sicuro fallire verso impostazioni prudenti
(``DEBUG=False``) che verso impostazioni permissive.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
