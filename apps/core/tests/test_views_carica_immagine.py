"""Upload immagini per l'editor Rich Text dei template email
(M-tabelle-immagini): perimetro D-11 (come ImpostazioniPiattaformaView),
validazione Pillow, limite di dimensione."""

import datetime
import io

import pytest
from allauth.mfa.models import Authenticator
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import Delega, Ruolo, StatoUtente, TipoUtente, Utente
from apps.core.models import ImmagineTemplateEmail

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


def _immagine_valida(nome: str = "test.png") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buffer, format="PNG")
    return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")


class TestCaricaImmagine:
    def test_segreteria_diretta_carica_immagine_valida(self, client, segreteria, settings):
        settings.SITE_URL = "https://catello.example.org"
        client.force_login(segreteria)

        response = client.post(
            "/impostazioni/template-email/carica-immagine/", {"file": _immagine_valida()}
        )

        assert response.status_code == 200
        dati = response.json()
        assert dati["location"].startswith("https://catello.example.org/media/")
        immagine = ImmagineTemplateEmail.objects.get()
        assert immagine.caricata_da == segreteria

    def test_anonimo_non_carica(self, client):
        response = client.post(
            "/impostazioni/template-email/carica-immagine/", {"file": _immagine_valida()}
        )
        assert response.status_code == 302
        assert ImmagineTemplateEmail.objects.count() == 0

    def test_cg_non_autorizzato(self, client):
        from apps.organizzazione.models import Gruppo

        utente = _persona("cg@campania.agesci.it")
        _con_mfa_configurata(utente)
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        client.force_login(utente)

        response = client.post(
            "/impostazioni/template-email/carica-immagine/", {"file": _immagine_valida()}
        )
        assert response.status_code == 403
        assert ImmagineTemplateEmail.objects.count() == 0

    def test_delegato_non_autorizzato(self, client, segreteria):
        # D-11: stesso perimetro di ImpostazioniPiattaformaView, esclusi i delegati.
        delegato = _persona("delegato@campania.agesci.it")
        _con_mfa_configurata(delegato)
        ruolo = Ruolo.objects.get(utente=segreteria)
        Delega.objects.create(
            delegante=segreteria,
            delegato=delegato,
            ruolo=ruolo,
            data_fine=datetime.date.today() + datetime.timedelta(days=30),
        )
        client.force_login(delegato)

        response = client.post(
            "/impostazioni/template-email/carica-immagine/", {"file": _immagine_valida()}
        )
        assert response.status_code == 403
        assert ImmagineTemplateEmail.objects.count() == 0

    def test_file_non_immagine_rifiutato(self, client, segreteria):
        client.force_login(segreteria)
        file_finto = SimpleUploadedFile(
            "finto.png", b"non e' davvero un'immagine", content_type="image/png"
        )

        response = client.post(
            "/impostazioni/template-email/carica-immagine/", {"file": file_finto}
        )

        assert response.status_code == 400
        assert ImmagineTemplateEmail.objects.count() == 0

    def test_nessun_file_rifiutato(self, client, segreteria):
        client.force_login(segreteria)
        response = client.post("/impostazioni/template-email/carica-immagine/", {})
        assert response.status_code == 400

    def test_file_troppo_grande_rifiutato(self, client, segreteria, monkeypatch):
        import apps.core.views as views_module

        monkeypatch.setattr(views_module, "DIMENSIONE_MASSIMA_IMMAGINE_BYTES", 10)
        client.force_login(segreteria)

        response = client.post(
            "/impostazioni/template-email/carica-immagine/", {"file": _immagine_valida()}
        )

        assert response.status_code == 400
        assert ImmagineTemplateEmail.objects.count() == 0
