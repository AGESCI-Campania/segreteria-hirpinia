"""Test dello strip dei codici di decisione (D-NN/A-NN) dai messaggi
mostrati all'utente (issue GitHub #4)."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase

from apps.core.messaggi import messaggi_per_campo, messaggio_utente


class MessaggioUtenteTest(SimpleTestCase):
    def test_nessun_codice_resta_invariato(self):
        exc = ValidationError("Errore generico senza codice.")
        self.assertEqual(messaggio_utente(exc), "Errore generico senza codice.")

    def test_codice_singolo_rimosso(self):
        exc = ValidationError("La campagna non è APERTA (D-12).")
        self.assertEqual(messaggio_utente(exc), "La campagna non è APERTA")

    def test_doppio_codice_rimosso(self):
        exc = ValidationError("Respingimento senza causale non possibile (D-12/D-24).")
        self.assertEqual(messaggio_utente(exc), "Respingimento senza causale non possibile")

    def test_codice_misto_rimosso(self):
        exc = ValidationError("Trasferimento rilevato (D-24/A-10).")
        self.assertEqual(messaggio_utente(exc), "Trasferimento rilevato")

    def test_codice_non_in_coda_non_rimosso(self):
        exc = ValidationError("Vedi (D-12) per il dettaglio della regola applicata.")
        self.assertEqual(
            messaggio_utente(exc), "Vedi (D-12) per il dettaglio della regola applicata."
        )

    def test_permission_denied_senza_messages(self):
        exc = PermissionDenied("Azione riservata a SEGRETERIA/ADMIN/RDZ (D-12).")
        self.assertEqual(messaggio_utente(exc), "Azione riservata a SEGRETERIA/ADMIN/RDZ")


class MessaggiPerCampoTest(SimpleTestCase):
    def test_validation_error_con_dict(self):
        # (M15) è un riferimento di milestone, non un codice di decisione
        # D-NN/A-NN: non rientra nello scopo della issue #4, resta invariato.
        exc = ValidationError(
            {
                "data_inizio": ["Fuori dalla finestra dell'anno associativo 2026 (D-10)."],
                "descrizione_altro": ['Obbligatorio quando la tipologia è "Altro" (M15).'],
            }
        )
        self.assertEqual(
            messaggi_per_campo(exc),
            {
                "data_inizio": "Fuori dalla finestra dell'anno associativo 2026",
                "descrizione_altro": 'Obbligatorio quando la tipologia è "Altro" (M15).',
            },
        )

    def test_validation_error_piatta_ritorna_none(self):
        exc = ValidationError("La campagna non è aperta all'inserimento (D-21).")
        self.assertIsNone(messaggi_per_campo(exc))

    def test_permission_denied_ritorna_none(self):
        exc = PermissionDenied("Azione preclusa (D-27).")
        self.assertIsNone(messaggi_per_campo(exc))
