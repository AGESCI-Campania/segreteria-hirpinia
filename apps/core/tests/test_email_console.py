from io import StringIO

from django.core.mail import EmailMessage

from apps.core.email.console import ConsoleFileEmailBackend


def test_scrive_sul_file_di_log(tmp_path, settings):
    log_file = tmp_path / "email-console.log"
    settings.EMAIL_CONSOLE_LOG_FILE = log_file

    backend = ConsoleFileEmailBackend(stream=StringIO())
    message = EmailMessage(
        subject="Oggetto di prova",
        body="Corpo di prova.",
        from_email="mittente@example.com",
        to=["destinatario@example.com"],
    )

    inviate = backend.send_messages([message])

    assert inviate == 1
    assert log_file.exists()
    contenuto = log_file.read_text(encoding="utf-8")
    assert "Oggetto di prova" in contenuto
    assert "destinatario@example.com" in contenuto


def test_scrive_anche_sullo_stream_console(tmp_path, settings):
    settings.EMAIL_CONSOLE_LOG_FILE = tmp_path / "email-console.log"
    stream = StringIO()

    backend = ConsoleFileEmailBackend(stream=stream)
    message = EmailMessage(
        subject="Oggetto di prova",
        body="Corpo di prova.",
        from_email="mittente@example.com",
        to=["destinatario@example.com"],
    )
    backend.send_messages([message])

    assert "Oggetto di prova" in stream.getvalue()


def test_crea_le_cartelle_mancanti(tmp_path, settings):
    log_file = tmp_path / "sottocartella" / "email-console.log"
    settings.EMAIL_CONSOLE_LOG_FILE = log_file

    backend = ConsoleFileEmailBackend(stream=StringIO())
    message = EmailMessage(
        subject="Oggetto",
        body="Corpo.",
        from_email="mittente@example.com",
        to=["destinatario@example.com"],
    )
    backend.send_messages([message])

    assert log_file.exists()


def test_accumula_piu_invii_senza_sovrascrivere(tmp_path, settings):
    log_file = tmp_path / "email-console.log"
    settings.EMAIL_CONSOLE_LOG_FILE = log_file

    backend = ConsoleFileEmailBackend(stream=StringIO())
    primo = EmailMessage("Primo", "Corpo 1.", "a@example.com", ["dest@example.com"])
    secondo = EmailMessage("Secondo", "Corpo 2.", "a@example.com", ["dest@example.com"])

    backend.send_messages([primo])
    backend.send_messages([secondo])

    contenuto = log_file.read_text(encoding="utf-8")
    assert "Primo" in contenuto
    assert "Secondo" in contenuto
