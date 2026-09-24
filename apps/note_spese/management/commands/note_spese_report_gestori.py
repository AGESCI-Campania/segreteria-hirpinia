"""D-64: valuta se è il momento di inviare il report periodico ai gestori.
Comando puro, nessuna logica qui — delega interamente a
`report_gestori.py::invia_report_gestori()`. Pensato per essere invocato
più volte al giorno da un processo esterno (loop nel container di
produzione, stesso pattern già in uso per `pulizia-sessioni` e
`note_spese_promemoria` in `compose.prod.yaml`) — a differenza di
`note_spese_promemoria`, qui l'orario configurato va rispettato, quindi
serve un loop più fitto: `invia_report_gestori()` si protegge da sé contro
i doppi invii nello stesso giorno."""

from django.core.management.base import BaseCommand

from apps.note_spese.report_gestori import invia_report_gestori


class Command(BaseCommand):
    help = (
        "Invia il report periodico ai gestori se oggi/ora rientrano nella "
        "schedulazione configurata (D-64). No-op altrimenti."
    )

    def handle(self, *args, **options):
        inviati = invia_report_gestori()
        self.stdout.write(self.style.SUCCESS(f"Report inviati: {inviati}"))
