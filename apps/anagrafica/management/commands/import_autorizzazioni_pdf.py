from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Utente
from apps.accounts.permessi import ruoli_effettivi
from apps.anagrafica.importazione import RUOLI_IMPORT_ANAGRAFICA
from apps.anagrafica.importazione_autorizzazioni import (
    applica_piano_autorizzazioni,
    costruisci_piano_autorizzazioni,
    estrai_pdf_da_file_caricati,
)


class Command(BaseCommand):
    help = (
        "Importa le autorizzazioni PDF di gruppo (§6.2), da singoli file .pdf e/o "
        "archivi .zip. Senza --conferma mostra solo l'anteprima, senza scrivere nulla."
    )

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", type=Path)
        parser.add_argument(
            "--utente",
            required=True,
            help="Email dell'utente che esegue l'import, per verificarne il perimetro.",
        )
        parser.add_argument(
            "--conferma",
            action="store_true",
            help="Applica l'importazione. Senza questo flag: solo anteprima (dry-run).",
        )

    def handle(self, *args, **options):
        paths: list[Path] = options["paths"]
        email: str = options["utente"]
        conferma: bool = options["conferma"]

        try:
            utente = Utente.objects.get(email__iexact=email)
        except Utente.DoesNotExist as exc:
            raise CommandError(f"Nessun utente con email {email}.") from exc

        if not any(r.tipo in RUOLI_IMPORT_ANAGRAFICA for r in ruoli_effettivi(utente)):
            raise CommandError(
                f"{email} non ha un ruolo abilitato all'import delle autorizzazioni "
                f"({', '.join(sorted(RUOLI_IMPORT_ANAGRAFICA))})."
            )

        file_caricati: list[tuple[str, bytes]] = []
        for path in paths:
            if not path.exists():
                raise CommandError(f"File non trovato: {path}")
            file_caricati.append((path.name, path.read_bytes()))

        pdf_caricati, anomalie_estrazione = estrai_pdf_da_file_caricati(file_caricati)
        piano = costruisci_piano_autorizzazioni(pdf_caricati)
        piano.anomalie = anomalie_estrazione + piano.anomalie

        if not piano.valido:
            self.stderr.write(self.style.ERROR("Nessun PDF di autorizzazione riconosciuto:"))
            for a in piano.anomalie:
                self.stderr.write(f"  [{a.livello}] {a.campo}: {a.dettaglio}")
            raise CommandError("Import interrotto.")

        self._stampa_anteprima(piano)

        if not conferma:
            self.stdout.write(
                self.style.WARNING(
                    "Anteprima (dry-run): nessuna scrittura. Rilancia con --conferma per applicare."
                )
            )
            return

        importazione = applica_piano_autorizzazioni(piano, utente=utente)
        self.stdout.write(self.style.SUCCESS(f"Importazione #{importazione.pk} completata."))

    def _stampa_anteprima(self, piano) -> None:
        self.stdout.write(f"PDF riconosciuti: {piano.pdf_processati}")
        self.stdout.write(f"Gruppi applicabili: {len(piano.pdf_vincitori)}")
        self.stdout.write(f"Incarichi da scrivere: {len(piano.incarichi)}")
        if piano.anomalie:
            self.stdout.write(self.style.WARNING(f"Anomalie: {len(piano.anomalie)}"))
            for a in piano.anomalie:
                self.stdout.write(f"  [{a.livello}] {a.campo}: {a.dettaglio}")
