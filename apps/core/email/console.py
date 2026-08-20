"""Backend "console" con persistenza su file, per lo sviluppo.

Il backend console standard di Django stampa le email solo sullo stream del
processo che le invia. Nel flusso reale di sviluppo (verifica registrazione,
inviti OTP, reset password) l'email va spesso letta più tardi o in un altro
terminale rispetto a quello con ``runserver``: questo backend fa esattamente
ciò che fa il backend console standard, in più tiene traccia di ogni invio in
un file di log leggibile con un editor o ``tail -f``.

Non pensato per la produzione: nessuna rotazione, nessun controllo di
dimensione del file. Il provider ``console`` è comunque solo di sviluppo (§ 8
del documento di progettazione).
"""

from pathlib import Path

from django.conf import settings
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend

DEFAULT_LOG_FILE = "log/email-console.log"


class ConsoleFileEmailBackend(ConsoleEmailBackend):
    """Backend console che duplica ogni messaggio anche su file."""

    def write_message(self, message):
        super().write_message(message)
        self._scrivi_su_file(message)

    def _scrivi_su_file(self, message):
        percorso = self._percorso_log()
        percorso.parent.mkdir(parents=True, exist_ok=True)

        msg = message.message()
        charset = msg.get_charset().get_output_charset() if msg.get_charset() else "utf-8"
        msg_data = msg.as_bytes().decode(charset)

        with percorso.open("a", encoding="utf-8") as log_file:
            log_file.write(msg_data)
            log_file.write("\n" + "-" * 79 + "\n")

    @staticmethod
    def _percorso_log() -> Path:
        valore = getattr(settings, "EMAIL_CONSOLE_LOG_FILE", None)
        if valore:
            return Path(valore)
        return Path(settings.BASE_DIR) / DEFAULT_LOG_FILE
