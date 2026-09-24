"""D-59: riprova le copie su Google Drive in attesa o fallite. Comando
puro, nessuna logica qui — delega interamente a
`drive_replica.py::riconcilia_copie_drive()`. Pensato per essere invocato
periodicamente da un loop esterno (stesso pattern di
`note_spese_promemoria`/`note_spese_report_gestori` in
`compose.prod.yaml`), mai da Celery/Redis (D-17, deciso con Andrea il
2026-09-24 di non introdurli)."""

from django.core.management.base import BaseCommand

from apps.note_spese.drive_replica import riconcilia_copie_drive


class Command(BaseCommand):
    help = (
        "Riprova le copie su Google Drive in attesa o fallite (D-59). "
        "No-op se la replica non è configurata (V-8)."
    )

    def handle(self, *args, **options):
        riuscite = riconcilia_copie_drive()
        self.stdout.write(self.style.SUCCESS(f"Copie riuscite: {riuscite}"))
