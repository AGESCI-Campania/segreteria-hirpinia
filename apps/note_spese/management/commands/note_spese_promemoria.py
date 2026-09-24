"""D-63: invia i promemoria del giorno. Comando puro, nessuna logica qui —
delega interamente a `promemoria.py::invia_promemoria()` (funzione pura
chiamata dal comando, mai il contrario, stesso principio già applicato alle
importazioni). Pensato per essere invocato una volta al giorno da un
processo esterno (loop nel container di produzione, stesso pattern già in
uso per `pulizia-sessioni` in `compose.prod.yaml`) — mai da Celery/Redis
(D-17, deciso con Andrea il 2026-09-24 di non introdurli)."""

from django.core.management.base import BaseCommand

from apps.note_spese.promemoria import invia_promemoria


class Command(BaseCommand):
    help = (
        "Invia i promemoria del giorno ai capi con note spese che richiedono una loro "
        "azione (D-63). No-op se oggi non è un giorno di promemoria."
    )

    def handle(self, *args, **options):
        inviati = invia_promemoria()
        self.stdout.write(self.style.SUCCESS(f"Promemoria inviati: {inviati}"))
