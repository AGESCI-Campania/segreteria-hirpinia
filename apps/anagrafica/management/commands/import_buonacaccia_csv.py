from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Utente
from apps.accounts.permessi import ruoli_effettivi
from apps.anagrafica.importazione import RUOLI_IMPORT_ANAGRAFICA, applica_piano, costruisci_piano
from apps.anagrafica.parser.buonacaccia import parse_csv


class Command(BaseCommand):
    help = (
        'Importa il CSV "Ricerca Soci" di Buona Caccia (§6.1). Senza --conferma '
        "mostra solo l'anteprima, senza scrivere nulla."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
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
        path: Path = options["path"]
        email: str = options["utente"]
        conferma: bool = options["conferma"]

        try:
            utente = Utente.objects.get(email__iexact=email)
        except Utente.DoesNotExist as exc:
            raise CommandError(f"Nessun utente con email {email}.") from exc

        if not any(r.tipo in RUOLI_IMPORT_ANAGRAFICA for r in ruoli_effettivi(utente)):
            raise CommandError(
                f"{email} non ha un ruolo abilitato all'import anagrafico "
                f"({', '.join(sorted(RUOLI_IMPORT_ANAGRAFICA))})."
            )

        if not path.exists():
            raise CommandError(f"File non trovato: {path}")

        risultato = parse_csv(path)
        piano = costruisci_piano(risultato)

        if not piano.valido:
            self.stderr.write(self.style.ERROR("Impossibile determinare l'anno scout dal file:"))
            for messaggio in risultato.anomalie_file:
                self.stderr.write(f"  - {messaggio}")
            raise CommandError("Import interrotto.")

        self._stampa_anteprima(piano)

        if not conferma:
            self.stdout.write(
                self.style.WARNING(
                    "Anteprima (dry-run): nessuna scrittura. Rilancia con --conferma per applicare."
                )
            )
            return

        with open(path, "rb") as flusso:
            file_originale = File(flusso, name=path.name)
            importazione = applica_piano(piano, file_originale=file_originale, utente=utente)

        self.stdout.write(self.style.SUCCESS(f"Importazione #{importazione.pk} completata."))

    def _stampa_anteprima(self, piano) -> None:
        trasferimenti = sum(1 for c in piano.censimenti if c.trasferimento_da)
        self.stdout.write(f"Anno scout: {piano.anno_scout}")
        self.stdout.write(f"Gruppi nel file: {len(piano.gruppi)}")
        self.stdout.write(f"Capi nel file: {len(piano.capi)}")
        self.stdout.write(f"Censimenti da scrivere: {len(piano.censimenti)}")
        self.stdout.write(f"Voci allowlist da aggiornare: {len(piano.allowlist)}")
        self.stdout.write(f"Capi da disattivare: {len(piano.capi_da_disattivare)}")
        self.stdout.write(f"Trasferimenti rilevati: {trasferimenti}")
        if piano.anomalie:
            self.stdout.write(self.style.WARNING(f"Anomalie: {len(piano.anomalie)}"))
            for a in piano.anomalie:
                self.stdout.write(f"  [{a.livello}] riga {a.numero_riga} {a.campo}: {a.dettaglio}")
